"""
爬虫基类 — 所有平台爬虫的公共逻辑

职责:
1. HTTP 请求管理 (重试、超时、UA 轮换)
2. 原始数据快照保存 (溯源)
3. 限速控制
"""

import time
import random
import hashlib
import json
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from src.config import CRAWL_CONFIG
from src.storage.database import get_session
from src.storage.repository import save_raw_snapshot


class BaseCrawler(ABC):
    """爬虫基类"""

    platform: str = "base"

    def __init__(self):
        self._client: httpx.Client | None = None
        self._last_request_time = 0

    # ---------- HTTP 客户端 ----------

    def _get_client(self) -> httpx.Client:
        """获取 HTTP 客户端 (懒加载)"""
        if self._client is None:
            self._client = httpx.Client(
                timeout=CRAWL_CONFIG["timeout"],
                follow_redirects=True,
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> dict:
        """构建请求头"""
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    # ---------- 限速控制 ----------

    def _rate_limit(self):
        """限速 — 两次请求之间随机间隔"""
        delay_min, delay_max = CRAWL_CONFIG["request_delay"]
        elapsed = time.time() - self._last_request_time
        min_delay = delay_min
        if elapsed < min_delay:
            sleep_time = random.uniform(min_delay, delay_max) + (min_delay - elapsed)
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    # ---------- 请求封装 ----------

    def _request(self, url: str, params: dict | None = None) -> httpx.Response:
        """发送 GET 请求 (带重试)"""
        self._rate_limit()
        last_exception = None
        for attempt in range(CRAWL_CONFIG["max_retries"]):
            try:
                resp = self._get_client().get(url, params=params)
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as e:
                last_exception = e
                wait = 2 ** attempt  # 指数退避
                time.sleep(wait)
        raise last_exception  # type: ignore

    # ---------- 快照保存 ----------

    def _save_snapshot(
        self, task_id: int, html: str = "",
        api_response: dict | None = None, product_id: int | None = None,
    ) -> str:
        """保存原始快照，返回内容哈希作为指纹"""
        session = get_session()
        try:
            content = html or json.dumps(api_response, ensure_ascii=False)
            fingerprint = hashlib.md5(content.encode()).hexdigest()

            save_raw_snapshot(
                session=session,
                task_id=task_id,
                platform=self.platform,
                raw_html=html if html else None,
                raw_json=api_response,
                product_id=product_id,
            )
            return fingerprint
        finally:
            session.close()

    # ---------- 抽象方法 ----------

    @abstractmethod
    def search_products(self, keyword: str, task_id: int) -> list[dict]:
        """
        根据关键词搜索商品列表
        Args:
            keyword: 搜索关键词
            task_id: 关联的爬取任务 ID
        Returns:
            商品字典列表，每个包含: title, price, product_id, url, shop_name 等
        """
        ...

    @abstractmethod
    def parse_product_list(self, html: str) -> list[dict]:
        """从 HTML 解析商品列表"""
        ...

    # ---------- 清理 ----------

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
