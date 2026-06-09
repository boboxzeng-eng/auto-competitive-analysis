"""
京东爬虫 — 搜索商品列表、解析商品信息

策略:
1. Playwright 渲染搜索页 (处理 JS 加载)
2. 解析实际 DOM 结构提取商品数据
3. API 接口辅助获取额外信息
4. 支持多页抓取
"""

import json
import re
import time
import random
from datetime import datetime

from playwright.sync_api import sync_playwright, Page, Browser

from src.crawlers.base import BaseCrawler
from src.config import CRAWL_CONFIG


class JDCrawler(BaseCrawler):
    """京东商品爬虫 - Playwright 增强版"""

    platform = "jd"
    SEARCH_URL = "https://search.jd.com/Search"

    # 京东移动端搜索 API (JSON 响应)
    SEARCH_API = "https://so.m.jd.com/ware/search.action"

    def __init__(self, headless: bool = True):
        super().__init__()
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    # ---------- 浏览器管理 ----------

    def _init_browser(self):
        """初始化 Playwright 浏览器"""
        if self._browser is not None:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

    def _new_page(self) -> Page:
        """创建新页面 (带反检测)"""
        self._init_browser()
        context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        # 移除 webdriver 标记
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
        """)
        page = context.new_page()
        return page

    # ---------- 搜索入口 ----------

    def search_products(
        self, keyword: str, task_id: int, max_pages: int = 2,
    ) -> list[dict]:
        """
        搜索京东商品 (Playwright 渲染)

        Args:
            keyword: 搜索关键词
            task_id: 爬取任务 ID
            max_pages: 最大页数 (每页约 30 件)
        """
        all_products = []

        # 策略 A: 移动端 API (快速，JSON)
        api_products = self._search_via_api(keyword, task_id)
        if api_products:
            all_products.extend(api_products)

        # 策略 B: Playwright 渲染 PC 搜索页 (完整数据)
        if len(all_products) < 10:
            pw_products = self._search_via_playwright(keyword, task_id, max_pages)
            # 合并去重
            existing_ids = {p["product_id"] for p in all_products}
            for p in pw_products:
                if p["product_id"] not in existing_ids:
                    all_products.append(p)

        return all_products[:CRAWL_CONFIG["max_products_per_search"]]

    # ---------- 策略 A: 移动端 API ----------

    def _search_via_api(self, keyword: str, task_id: int) -> list[dict]:
        """通过 JD 移动端搜索 API 获取"""
        params = {
            "keyword": keyword,
            "page": 1,
            "pageSize": 30,
            "sort_type": "sort_default",
        }
        try:
            # 使用 httpx 客户端
            headers = {
                "Referer": "https://m.jd.com/",
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/16.0 Mobile/15E148 Safari/604.1"
                ),
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

    # ---------- 策略 B: Playwright 渲染 ----------

    def _search_via_playwright(
        self, keyword: str, task_id: int, max_pages: int = 2,
    ) -> list[dict]:
        """通过 Playwright 渲染搜索页"""
        all_products = []
        page = None

        try:
            page = self._new_page()

            for page_num in range(1, max_pages + 1):
                url = f"{self.SEARCH_URL}?keyword={keyword}&page={page_num}"
                print(f"[JD PW] 抓取第 {page_num} 页: {url}")

                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    # 等商品列表渲染
                    page.wait_for_selector(".gl-item", timeout=10000)

                    # 滚动加载
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(random.uniform(1.0, 2.0))

                    # 保存快照
                    html = page.content()
                    self._save_snapshot(task_id=task_id, html=html)

                    # 解析
                    products = self._parse_playwright_page(page)
                    all_products.extend(products)

                    if len(products) < 20:
                        # 最后一页，数据不足
                        break

                    # 翻页间隔
                    time.sleep(random.uniform(2, 4))

                except Exception as e:
                    print(f"[JD PW] 第 {page_num} 页失败: {e}")
                    break

            return all_products

        except Exception as e:
            print(f"[JD PW] Playwright 初始化失败: {e}")
            return []
        finally:
            if page:
                try:
                    page.context.close()
                except Exception:
                    pass

    def _parse_playwright_page(self, page: Page) -> list[dict]:
        """从 Playwright 页面提取商品信息"""
        products = []

        items = page.query_selector_all(".gl-warp .gl-item")
        if not items:
            items = page.query_selector_all(".goods-list-v2 .gl-item")

        for item in items:
            try:
                product = self._extract_product_from_element(item)
                if product and product.get("title"):
                    products.append(product)
            except Exception as e:
                print(f"[JD PW] 解析商品失败: {e}")
                continue

        return products

    def _extract_product_from_element(self, element) -> dict | None:
        """从 DOM 元素提取单个商品信息"""
        try:
            # 商品 ID
            sku = element.get_attribute("data-sku") or ""

            # 标题
            title_el = element.query_selector(".p-name a em") or \
                       element.query_selector(".p-name em") or \
                       element.query_selector("[data-title]")
            title = ""
            if title_el:
                title = title_el.inner_text().strip()

            if not title:
                return None

            # 价格
            price_el = element.query_selector(".p-price i") or \
                       element.query_selector(".p-price strong") or \
                       element.query_selector(".p-price")
            price = None
            if price_el:
                price_text = price_el.inner_text().strip()
                price = self._parse_price(price_text)

            # 原价
            orig_el = element.query_selector(".p-price del") or \
                      element.query_selector(".p-market-price")
            original_price = None
            if orig_el:
                orig_text = orig_el.inner_text().strip()
                original_price = self._parse_price(orig_text)

            # 店铺
            shop_el = element.query_selector(".p-shop a") or \
                      element.query_selector(".curr-shop") or \
                      element.query_selector("[data-shop_name]")
            shop_name = ""
            if shop_el:
                shop_name = shop_el.inner_text().strip()

            # 评价数
            commit_el = element.query_selector(".p-commit a") or \
                        element.query_selector(".p-commit strong")
            comment_count = None
            if commit_el:
                comment_count = self._parse_int(commit_el.inner_text())

            # 图片
            img_el = element.query_selector(".p-img img")
            image_url = ""
            if img_el:
                image_url = img_el.get_attribute("src") or \
                            img_el.get_attribute("data-lazy-img") or ""

            return {
                "platform": "jd",
                "product_id": str(sku),
                "title": title,
                "price": price,
                "original_price": original_price,
                "sales_volume": None,  # PC 搜索页通常无销量
                "shop_name": shop_name,
                "brand": self._guess_brand(title),
                "image_url": str(image_url) if image_url else "",
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

        # 多种可能的数据结构
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
                product = {
                    "platform": "jd",
                    "product_id": ware_id,
                    "title": title,
                    "price": self._parse_price(
                        item.get("jdPrice") or item.get("price")
                    ),
                    "original_price": self._parse_price(
                        item.get("mUrl")
                    ),
                    "sales_volume": self._parse_int(
                        item.get("saleNum")
                        or item.get("inOrderCount30Days")
                        or item.get("orderCount")
                    ),
                    "shop_name": item.get("shopName", item.get("shop_name", "")),
                    "brand": item.get("brandName", self._guess_brand(title)),
                    "image_url": (
                        f"https://img14.360buyimg.com/n0/{item.get('imageurl')}"
                        if item.get("imageurl") else ""
                    ),
                    "url": f"https://item.jd.com/{ware_id}.html" if ware_id else "",
                    "rating": self._parse_float(item.get("goodRate")),
                    "comment_count": self._parse_int(
                        item.get("commentCount") or item.get("commCount")
                    ),
                    "crawled_at": datetime.now().isoformat(),
                }
                products.append(product)
            except Exception as e:
                print(f"[JD API] 解析商品失败: {e}")
                continue

        return products

    # ---------- HTML 解析 (兼容旧接口) ----------

    def parse_product_list(self, html: str) -> list[dict]:
        """从 HTML 解析 (委托给内部解析)"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        products = []

        items = soup.select(".gl-warp .gl-item")
        if not items:
            items = soup.select(".goods-list-v2 .gl-item")

        for item in items:
            try:
                sku = item.get("data-sku", "")
                title_el = item.select_one(".p-name a em") or item.select_one(".p-name em")
                title = title_el.get_text(strip=True) if title_el else ""

                price_el = item.select_one(".p-price i") or item.select_one(".p-price strong")
                price_text = price_el.get_text(strip=True) if price_el else "0"

                shop_el = item.select_one(".p-shop a") or item.select_one(".curr-shop")
                shop = shop_el.get_text(strip=True) if shop_el else ""

                products.append({
                    "platform": "jd",
                    "product_id": str(sku),
                    "title": title,
                    "price": self._parse_price(price_text),
                    "original_price": None,
                    "sales_volume": None,
                    "shop_name": shop,
                    "brand": self._guess_brand(title),
                    "image_url": "",
                    "url": f"https://item.jd.com/{sku}.html" if sku else "",
                    "rating": None,
                    "comment_count": None,
                    "crawled_at": datetime.now().isoformat(),
                })
            except Exception as e:
                print(f"[JD HTML] 解析商品失败: {e}")
                continue

        return products

    # ---------- 品牌推测 ----------

    @staticmethod
    def _guess_brand(title: str) -> str:
        """从标题推测品牌"""
        known_brands = [
            "华为", "小米", "OPPO", "vivo", "三星", "苹果", "荣耀",
            "联想", "戴尔", "惠普", "华硕", "海尔", "美的", "格力",
            "海信", "TCL", "索尼", "飞利浦", "松下",
        ]
        for brand in known_brands:
            if brand in title:
                return brand
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
                num = float(text.replace("万", "").replace("+", ""))
                return int(num * 10000)
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
