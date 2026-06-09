"""
竞品匹配引擎

根据 CompetitiveProfile 对每个商品进行多维度打分:
1. 价格相似度 (price_similarity)     — 价格越接近得分越高
2. 品类匹配度 (category_match)       — 品类关键词命中
3. 品牌竞争度 (brand_competition)    — 是否与对标品牌互为竞品
4. 规格相似度 (spec_similarity)      — 标题中规格关键词匹配

得分公式:
  score = w1*p + w2*c + w3*b + w4*s

score >= 阈值 → 竞品
"""

from typing import Optional

from src.config import (
    BRAND_COMPETITOR_MAP,
    DEFAULT_MATCH_WEIGHTS,
    COMPETITOR_SCORE_THRESHOLD,
    PRESET_CATEGORIES,
)


class CompetitiveMatcher:
    """
    竞品匹配器

    用法:
        matcher = CompetitiveMatcher(profile)
        for product in products:
            score, details = matcher.evaluate(product)
            product["competitor_score"] = score
            product["match_details"] = details
            product["is_competitor"] = score >= matcher.threshold
    """

    def __init__(self, profile: dict):
        """
        Args:
            profile: CompetitiveProfile 字典
                {
                    "brand": "小米",
                    "category": "手机",
                    "price_min": 4000,
                    "price_max": 7000,
                    "key_specs": {"屏幕尺寸": "6.7英寸"},
                    "match_weights": {...},
                }
        """
        self.brand = profile.get("brand", "")
        self.category = profile.get("category", "")
        self.price_min = profile.get("price_min")
        self.price_max = profile.get("price_max")
        self.key_specs = profile.get("key_specs") or profile.get("specs_json") or {}
        self.weights = profile.get("match_weights") or profile.get("match_weights_json") or DEFAULT_MATCH_WEIGHTS
        self.threshold = COMPETITOR_SCORE_THRESHOLD

        # 竞品品牌列表
        self.competitor_brands: set[str] = set()
        if self.brand and self.brand in BRAND_COMPETITOR_MAP:
            self.competitor_brands = set(BRAND_COMPETITOR_MAP[self.brand])

        # 品类关键词
        self.category_keywords: list[str] = []
        if self.category in PRESET_CATEGORIES:
            cat_info = PRESET_CATEGORIES[self.category]
            if isinstance(cat_info, dict):
                self.category_keywords = cat_info.get("keywords", [self.category])
            else:
                self.category_keywords = cat_info

    # ---------- 主入口 ----------

    def evaluate(self, product: dict) -> tuple[float, dict]:
        """
        评估单个商品的竞品匹配度

        Returns:
            (score, details) — score 在 0-1 之间
        """
        scores = {}
        weights = self.weights

        # 1. 价格相似度
        scores["price_similarity"] = self._calc_price_similarity(product)
        # 2. 品类匹配度
        scores["category_match"] = self._calc_category_match(product)
        # 3. 品牌竞争度
        scores["brand_competition"] = self._calc_brand_competition(product)
        # 4. 规格相似度
        scores["spec_similarity"] = self._calc_spec_similarity(product)

        # 加权总分
        total = sum(
            weights.get(k, 0.25) * scores[k]
            for k in scores
        )
        total = round(min(total, 1.0), 4)

        return total, scores

    def evaluate_batch(self, products: list[dict]) -> list[dict]:
        """
        批量评估，原地更新 product 的竞品字段

        Returns:
            按竞品得分降序排列的 product 列表
        """
        for p in products:
            score, details = self.evaluate(p)
            p["competitor_score"] = score
            p["match_details"] = details
            p["is_competitor"] = score >= self.threshold

        # 排序: 竞品优先，然后按得分降序
        products.sort(
            key=lambda x: (x.get("is_competitor", False), x.get("competitor_score", 0)),
            reverse=True,
        )
        return products

    # ---------- 各维度计算 ----------

    def _calc_price_similarity(self, product: dict) -> float:
        """
        价格相似度

        逻辑: 价格在目标区间内 → 1.0
              价格偏离区间 → 按偏离比例递减
              超出 50% 范围 → 0 分
        """
        price = product.get("price")
        if price is None or price <= 0:
            return 0.0

        if self.price_min and self.price_max:
            if self.price_min <= price <= self.price_max:
                return 1.0

            # 计算偏离程度
            mid = (self.price_min + self.price_max) / 2
            span = self.price_max - self.price_min
            if span <= 0:
                return 0.0

            deviation = abs(price - mid) / (span / 2)
            if deviation >= 2.0:
                return 0.0
            return round(max(0, 1.0 - deviation * 0.5), 2)

        # 没有设价格区间 → 中性
        return 0.5

    def _calc_category_match(self, product: dict) -> float:
        """
        品类匹配度

        逻辑: 商品标题中包含品类关键词 → 匹配
              命中多个关键词 → 更高分
        """
        title = product.get("title", "")
        if not title or not self.category_keywords:
            return 0.5

        hits = sum(1 for kw in self.category_keywords if kw in title)
        if hits == 0:
            return 0.1  # 品类不匹配
        return min(1.0, 0.5 + hits * 0.25)

    def _calc_brand_competition(self, product: dict) -> float:
        """
        品牌竞争度

        逻辑: 商品品牌在对标品牌的竞品列表中 → 1.0
              同品牌 (自品) → 0.3 (可能是不同型号)
              其他品牌 → 0.0
        """
        product_brand = product.get("brand", "")
        if not product_brand or not self.brand:
            return 0.3  # 无品牌信息 → 中性

        if product_brand == self.brand:
            return 0.3  # 同品牌，可能是不同型号 (也算竞品但优先级低)

        if product_brand in self.competitor_brands:
            return 1.0  # 明确竞品品牌

        # 从标题推测品牌
        title = product.get("title", "")
        for comp_brand in self.competitor_brands:
            if comp_brand in title:
                return 0.8  # 标题中提及竞品品牌

        return 0.1  # 未知品牌

    def _calc_spec_similarity(self, product: dict) -> float:
        """
        规格相似度

        逻辑: 商品标题中命中关键规格关键词 → 加分
        """
        specs = self.key_specs
        if not specs:
            return 0.5  # 没有指定规格 → 中性

        title = product.get("title", "")
        if not title:
            return 0.0

        hits = 0
        for key, value in specs.items():
            # 检查标题中是否包含规格值
            if value and str(value) in title:
                hits += 1
            elif key and str(key) in title:
                hits += 0.5  # 命中规格名也算半分

        if len(specs) == 0:
            return 0.5

        return round(min(1.0, hits / len(specs)), 2)

    # ---------- 摘要 ----------

    def get_competitor_summary(self, products: list[dict]) -> dict:
        """生成竞品分析摘要"""
        competitors = [p for p in products if p.get("is_competitor")]
        non_competitors = [p for p in products if not p.get("is_competitor")]

        return {
            "total_crawled": len(products),
            "competitors_found": len(competitors),
            "non_competitors": len(non_competitors),
            "match_rate": (
                round(len(competitors) / len(products) * 100, 1)
                if products else 0
            ),
            "threshold": self.threshold,
            "weights_used": self.weights,
            "competitor_brands": list(self.competitor_brands),
            "top_competitors": [
                {
                    "title": p.get("title", "")[:50],
                    "price": p.get("price"),
                    "brand": p.get("brand", ""),
                    "score": p.get("competitor_score"),
                    "url": p.get("url", ""),
                }
                for p in sorted(
                    competitors,
                    key=lambda x: x.get("competitor_score", 0),
                    reverse=True,
                )[:10]
            ],
        }
