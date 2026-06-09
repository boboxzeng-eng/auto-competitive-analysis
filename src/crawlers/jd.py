"""
京东爬虫 — 合规框架

策略:
1. 优先使用移动端搜索 API (公开 JSON 接口)
2. 降级使用 Playwright 渲染 (以合规身份访问)
3. 遵守 robots.txt、速率限制
4. 支持价格区间筛选

注意: 此爬虫仅采集公开搜索列表页数据，供个人竞品分析使用。
"""

import re
import time
import random
from datetime import datetime
from urllib.parse import quote

from playwright.sync_api import sync_playwright, Page, Browser

from src.crawlers.base import BaseCrawler


class JDCrawler(BaseCrawler):
    """京东商品爬虫 — 合规版"""

    platform = "jd"
    BASE_URL = "https://www.jd.com"

    # 京东移动端搜索 API (公开接口)
    SEARCH_API = "https://so.m.jd.com/ware/search.action"

    def __init__(self, headless: bool = True):
        super().__init__()
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None

    # ---------- 浏览器管理 (合规) ----------

    def _init_browser(self):
        """初始化浏览器 — 使用合规 UA，不伪装 webdriver"""
        if self._browser is not None:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

    def _new_page(self) -> Page:
        """创建页面 — 合规身份"""
        self._init_browser()
        context = self._browser.new_context(
            user_agent=(
                "CompetitiveAnalysisBot/1.0 "
                "(Personal Research; https://github.com/boboxzeng-eng/auto-competitive-analysis)"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        return context.new_page()

    # ---------- 搜索入口 ----------

    def search_products(
        self, keyword: str, task_id: int,
        price_min: float = None, price_max: float = None,
        max_pages: int = 2,
    ) -> list[dict]:
        """
        搜索京东商品

        Args:
            keyword: 搜索关键词
            task_id: 爬取任务 ID
            price_min/max: 价格区间 (京东搜索支持价格筛选)
            max_pages: 最大页数
        """
        all_products = []

        # 策略 A: 移动端 API (优先)
        api_products = self._search_via_api(
            keyword, task_id, price_min, price_max,
        )
        if api_products:
            all_products.extend(api_products)

        # 策略 B: Playwright 渲染 (补充)
        if len(all_products) < 10:
            pw_products = self._search_via_playwright(
                keyword, task_id, max_pages, price_min, price_max,
            )
            existing_ids = {p["product_id"] for p in all_products}
            for p in pw_products:
                if p["product_id"] not in existing_ids:
                    all_products.append(p)

        return all_products

    # ---------- 策略 A: 移动端 API ----------

    def _search_via_api(
        self, keyword: str, task_id: int,
        price_min: float = None, price_max: float = None,
    ) -> list[dict]:
        """通过 JD 移动端公开 API 搜索"""
        params = {
            "keyword": keyword,
            "page": 1,
            "pageSize": 30,
            "sort_type": "sort_default",
        }
        # 京东移动端 API 支持价格区间参数
        if price_min is not None and price_max is not None:
            params["priceMin"] = str(price_min)
            params["priceMax"] = str(price_max)

        try:
            headers = {
                "User-Agent": (
                    "CompetitiveAnalysisBot/1.0 "
                    "(Personal Research; https://github.com/boboxzeng-eng/auto-competitive-analysis)"
                ),
                "Referer": "https://m.jd.com/",
            }
            resp = self._get_client().get(
                self.SEARCH_API, params=params, headers=headers,
            )
            resp.raise_for_status()

            self._save_snapshot(task_id=task_id, html=resp.text)

            data = resp.json()
            return self._parse_api_response(data)
        except Exception as e:
            print(f"[JD API] 搜索失败: {e}")
            return []

    # ---------- 策略 B: Playwright ----------

    def _search_via_playwright(
        self, keyword: str, task_id: int, max_pages: int = 2,
        price_min: float = None, price_max: float = None,
    ) -> list[dict]:
        """Playwright 渲染搜索页 — 合规访问"""
        all_products = []
        page = None

        try:
            page = self._new_page()

            for page_num in range(1, max_pages + 1):
                # 构建搜索 URL (京东 PC 端)
                url = f"https://search.jd.com/Search?keyword={quote(keyword)}&page={page_num}"
                # 价格区间
                if price_min is not None and price_max is not None:
                    url += f"&ev=exprice_{int(price_min)}-{int(price_max)}"

                print(f"[JD] 第 {page_num} 页: {url}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    # 等待商品列表
                    page.wait_for_selector(".gl-item", timeout=10000)

                    # 滚动加载 (遵循自然浏览速度)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(random.uniform(1.5, 2.5))

                    html = page.content()
                    self._save_snapshot(task_id=task_id, html=html)

                    products = self._parse_playwright_page(page)
                    all_products.extend(products)

                    if len(products) < 20:
                        break

                    time.sleep(random.uniform(3, 5))

                except Exception as e:
                    print(f"[JD] 第 {page_num} 页失败: {e}")
                    break

            return all_products

        except Exception as e:
            print(f"[JD] Playwright 失败: {e}")
            return []
        finally:
            if page:
                try:
                    page.context.close()
                except Exception:
                    pass

    def _parse_playwright_page(self, page: Page) -> list[dict]:
        """从 Playwright 页面提取商品"""
        products = []

        items = page.query_selector_all(".gl-warp .gl-item")
        if not items:
            items = page.query_selector_all(".goods-list-v2 .gl-item")

        for item in items:
            try:
                product = self._extract_from_element(item)
                if product and product.get("title"):
                    products.append(product)
            except Exception as e:
                continue

        return products

    def _extract_from_element(self, element) -> dict | None:
        """从 DOM 元素提取商品信息"""
        try:
            sku = element.get_attribute("data-sku") or ""

            title_el = (
                element.query_selector(".p-name a em")
                or element.query_selector(".p-name em")
            )
            title = title_el.inner_text().strip() if title_el else ""

            if not title:
                return None

            price_el = (
                element.query_selector(".p-price i")
                or element.query_selector(".p-price strong")
            )
            price = None
            if price_el:
                price = self._parse_price(price_el.inner_text().strip())

            shop_el = (
                element.query_selector(".p-shop a")
                or element.query_selector(".curr-shop")
            )
            shop_name = shop_el.inner_text().strip() if shop_el else ""

            commit_el = element.query_selector(".p-commit a")
            comment_count = None
            if commit_el:
                comment_count = self._parse_int(commit_el.inner_text())

            return {
                "platform": "jd",
                "product_id": str(sku),
                "title": title,
                "price": price,
                "original_price": None,
                "sales_volume": None,
                "shop_name": shop_name,
                "brand": self._guess_brand(title),
                "image_url": "",
                "url": f"https://item.jd.com/{sku}.html" if sku else "",
                "rating": None,
                "comment_count": comment_count,
                "crawled_at": datetime.now().isoformat(),
            }
        except Exception:
            return None

    # ---------- API 响应解析 ----------

    def _parse_api_response(self, data: dict) -> list[dict]:
        """解析移动端 API JSON"""
        products = []

        ware_list = (
            data.get("wareInfo", {}).get("wareList", [])
            or data.get("searchWareList", [])
            or data.get("goodsList", [])
            or data.get("wareList", [])
        )

        for item in ware_list:
            try:
                ware_id = str(item.get("wareId", ""))
                title = self._clean_html(
                    item.get("wname", item.get("wareName", ""))
                )
                products.append({
                    "platform": "jd",
                    "product_id": ware_id,
                    "title": title,
                    "price": self._parse_price(
                        item.get("jdPrice") or item.get("price")
                    ),
                    "original_price": self._parse_price(item.get("mUrl")),
                    "sales_volume": self._parse_int(
                        item.get("saleNum")
                        or item.get("inOrderCount30Days")
                        or item.get("orderCount")
                    ),
                    "shop_name": item.get("shopName", ""),
                    "brand": item.get("brandName") or self._guess_brand(title),
                    "image_url": f"https://img14.360buyimg.com/n0/{item.get('imageurl')}" if item.get("imageurl") else "",
                    "url": f"https://item.jd.com/{ware_id}.html" if ware_id else "",
                    "rating": self._parse_float(item.get("goodRate")),
                    "comment_count": self._parse_int(
                        item.get("commentCount") or item.get("commCount")
                    ),
                    "crawled_at": datetime.now().isoformat(),
                })
            except Exception:
                continue

        return products

    # ---------- 品牌推测 ----------

    @staticmethod
    def _guess_brand(title: str) -> str:
        known = [
            "华为", "小米", "OPPO", "vivo", "三星", "苹果", "荣耀",
            "联想", "戴尔", "惠普", "华硕", "海尔", "美的", "格力",
            "海信", "TCL", "索尼", "飞利浦", "松下",
        ]
        for b in known:
            if b in title:
                return b
        return ""

    # ---------- 工具方法 ----------

    @staticmethod
    def _clean_html(text: str) -> str:
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _parse_price(val) -> float | None:
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
        if val is None:
            return None
        if isinstance(val, int):
            return val
        text = str(val).replace(",", "").strip()
        if "万" in text:
            try:
                return int(float(text.replace("万", "").replace("+", "")) * 10000)
            except ValueError:
                return None
        try:
            return int(float(text))
        except ValueError:
            return None

    @staticmethod
    def _parse_float(val) -> float | None:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val).strip())
        except ValueError:
            return None

    # ---------- 清理 ----------

    def close(self):
        super().close()
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._browser = None
        self._playwright = None
