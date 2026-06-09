"""
京东爬虫 — 搜索商品列表、解析商品信息

京东搜索页: https://search.jd.com/Search?keyword=手机&page=1

注意: 京东搜索页需要 JS 渲染。MVP 阶段使用以下策略:
1. 优先用搜索 API 接口 (返回 JSON)
2. 降级使用 httpx + HTML 解析
3. 后续版本集成 Playwright 完全渲染
"""

import json
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.crawlers.base import BaseCrawler


class JDCrawler(BaseCrawler):
    """京东商品爬虫"""

    platform = "jd"
    BASE_URL = "https://search.jd.com"

    # 京东搜索 API (移动端接口，返回 JSON，反爬较宽松)
    SEARCH_API = "https://so.m.jd.com/ware/search.action"

    def __init__(self):
        super().__init__()
        self._client.headers.update({
            "Referer": "https://www.jd.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })

    # ---------- 搜索入口 ----------

    def search_products(self, keyword: str, task_id: int) -> list[dict]:
        """
        搜索京东商品

        策略: 先尝试移动端 API (JSON)，失败则回退 HTML 解析
        """
        products = self._search_via_api(keyword, task_id)
        if not products:
            products = self._search_via_html(keyword, task_id)
        return products

    def _search_via_api(self, keyword: str, task_id: int) -> list[dict]:
        """通过京东移动端搜索 API 获取商品"""
        params = {
            "keyword": keyword,
            "page": 1,
            "pageSize": 30,
            "sort_type": "sort_default",
        }
        try:
            resp = self._request(self.SEARCH_API, params=params)
            # 保存原始 API 响应快照
            raw_text = resp.text
            fingerprint = self._save_snapshot(
                task_id=task_id,
                html=raw_text,
            )
            data = resp.json()
            products = self._parse_api_response(data, keyword, task_id)
            return products
        except Exception as e:
            print(f"[JD API] 搜索失败: {e}")
            return []

    def _search_via_html(self, keyword: str, task_id: int) -> list[dict]:
        """通过京东 PC 搜索页 HTML 获取商品 (降级方案)"""
        url = f"{self.BASE_URL}/Search"
        params = {
            "keyword": keyword,
            "page": 1,
            "s": 1,  # 起始偏移
        }
        try:
            resp = self._request(url, params=params)
            self._save_snapshot(task_id=task_id, html=resp.text)
            return self.parse_product_list(resp.text)
        except Exception as e:
            print(f"[JD HTML] 搜索失败: {e}")
            return []

    # ---------- 解析逻辑 ----------

    def _parse_api_response(
        self, data: dict, keyword: str, task_id: int,
    ) -> list[dict]:
        """解析移动端 API 返回的 JSON"""
        products = []
        ware_list = data.get("wareInfo", {}).get("wareList", [])
        if not ware_list:
            # 尝试另一种数据结构
            ware_list = data.get("searchWareList", []) or data.get("goodsList", [])

        for item in ware_list:
            try:
                product = {
                    "platform": "jd",
                    "product_id": str(item.get("wareId", "")),
                    "title": self._clean_html(item.get("wname", item.get("wareName", ""))),
                    "price": self._parse_price(item.get("jdPrice", item.get("price"))),
                    "original_price": self._parse_price(item.get("mUrl", "")),
                    "sales_volume": self._parse_int(item.get("saleNum", item.get("inOrderCount30Days"))),
                    "shop_name": item.get("shopName", item.get("shop_name", "")),
                    "brand": item.get("brandName", ""),
                    "image_url": f"https://img14.360buyimg.com/n0/{item.get('imageurl', '')}" if item.get("imageurl") else "",
                    "url": f"https://item.jd.com/{item.get('wareId', '')}.html",
                    "rating": self._parse_float(item.get("goodRate")),
                    "comment_count": self._parse_int(item.get("commentCount", item.get("commCount"))),
                    "crawled_at": datetime.now().isoformat(),
                }
                products.append(product)
            except Exception as e:
                print(f"[JD] 解析商品失败: {e}")
                continue

        return products

    def parse_product_list(self, html: str) -> list[dict]:
        """从 PC 搜索页 HTML 解析商品列表"""
        products = []
        soup = BeautifulSoup(html, "lxml")

        items = soup.select(".gl-warp .gl-item")
        if not items:
            items = soup.select(".goods-list-v2 .gl-item")

        for item in items:
            try:
                # 商品 ID
                sku = item.get("data-sku", "") or item.select_one("[data-sku]")
                if hasattr(sku, 'get'):
                    sku = sku.get("data-sku", "")

                # 标题
                title_el = item.select_one(".p-name a em") or item.select_one(".p-name em")
                title = title_el.get_text(strip=True) if title_el else ""

                # 价格
                price_el = item.select_one(".p-price i") or item.select_one(".p-price strong")
                price_text = price_el.get_text(strip=True) if price_el else "0"

                # 店铺
                shop_el = item.select_one(".p-shop a") or item.select_one(".curr-shop")
                shop = shop_el.get_text(strip=True) if shop_el else ""

                product = {
                    "platform": "jd",
                    "product_id": str(sku),
                    "title": title,
                    "price": self._parse_price(price_text),
                    "original_price": None,
                    "sales_volume": None,
                    "shop_name": shop,
                    "brand": "",
                    "image_url": "",
                    "url": f"https://item.jd.com/{sku}.html" if sku else "",
                    "rating": None,
                    "comment_count": None,
                    "crawled_at": datetime.now().isoformat(),
                }
                products.append(product)
            except Exception as e:
                print(f"[JD HTML] 解析商品失败: {e}")
                continue

        return products

    # ---------- 工具方法 ----------

    @staticmethod
    def _clean_html(text: str) -> str:
        """去除 HTML 标签"""
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _parse_price(val) -> float | None:
        """解析价格"""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        text = str(val).replace("¥", "").replace("￥", "").strip()
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _parse_int(val) -> int | None:
        """解析整数"""
        if val is None:
            return None
        if isinstance(val, int):
            return val
        text = str(val).replace(",", "").strip()
        # 处理 "1.2万+" 这种格式
        if "万" in text:
            num = float(text.replace("万", "").replace("+", ""))
            return int(num * 10000)
        try:
            return int(float(text))
        except ValueError:
            return None

    @staticmethod
    def _parse_float(val) -> float | None:
        """解析浮点数"""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val).strip())
        except ValueError:
            return None
