"""
市场分析模块

分析维度:
- 品牌分布
- 店铺分布
- 销量排名
- 价格-销量关系
- 品类概况
"""

from collections import Counter
from typing import List

import pandas as pd


def analyze_market_overview(products: list[dict]) -> dict:
    """
    市场概况分析

    Returns:
        {
            "brand_distribution": {...},    # 品牌分布
            "shop_distribution": {...},     # 店铺分布
            "top_by_sales": [...],          # 销量 Top10
            "price_vs_sales_correlation": float,  # 价格-销量相关性
            "summary": str,                 # 文字摘要
        }
    """
    if not products:
        return {"error": "无商品数据"}

    df = pd.DataFrame(products)

    result = {}

    # 品牌分布
    brands = df["brand"].dropna().replace("", pd.NA).dropna()
    if not brands.empty:
        brand_counts = Counter(brands.tolist())
        result["brand_distribution"] = brand_counts.most_common(10)

    # 店铺分布
    shops = df["shop_name"].dropna().replace("", pd.NA).dropna()
    if not shops.empty:
        shop_counts = Counter(shops.tolist())
        result["shop_distribution"] = shop_counts.most_common(10)

    # 销量排名
    sales_df = df[df["sales_volume"].notna()].copy()
    if not sales_df.empty:
        top_sales = sales_df.nlargest(10, "sales_volume")
        result["top_by_sales"] = [
            {
                "title": row.get("title", "")[:40],
                "sales_volume": row.get("sales_volume"),
                "price": row.get("price"),
                "shop_name": row.get("shop_name", ""),
                "brand": row.get("brand", ""),
            }
            for _, row in top_sales.iterrows()
        ]

    # 价格-销量相关性
    price_sales = df[df["price"].notna() & df["sales_volume"].notna()]
    if len(price_sales) > 2:
        corr = price_sales["price"].corr(price_sales["sales_volume"])
        result["price_vs_sales_correlation"] = round(float(corr), 3)

    # 文字摘要
    result["summary"] = _generate_summary(result, len(products))

    return result


def _generate_summary(result: dict, total: int) -> str:
    """生成市场概况摘要"""
    parts = [f"共采集 {total} 个商品。"]

    if result.get("brand_distribution"):
        top_brand = result["brand_distribution"][0]
        parts.append(
            f"出现最多的品牌是「{top_brand[0]}」({top_brand[1]} 个商品)。"
        )

    if result.get("top_by_sales"):
        top = result["top_by_sales"][0]
        parts.append(f"销量最高的是「{top['title']}」。")

    if result.get("price_vs_sales_correlation") is not None:
        corr = result["price_vs_sales_correlation"]
        if corr > 0.3:
            parts.append("价格与销量呈正相关。")
        elif corr < -0.3:
            parts.append("价格与销量呈负相关，低价商品更受欢迎。")
        else:
            parts.append("价格与销量无明显相关性。")

    return "".join(parts)
