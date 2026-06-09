"""
爬虫基类 — 合规框架

原则:
- 遵守 robots.txt
- 明确声明爬虫身份 (不伪装浏览器)
- 合理速率限制
- 仅采集公开可访问的搜索列表页
- 数据仅供个人分析用途
"""

import time
import random
import hashlib
import json
from abc import ABC, abstractmethod
from urllib.parse import urljoin
from typing import Optional

import httpx

from src.config import COMPLIANCE_CONFIG
from src.storage.database import get_session
from src.storage.repository import save_raw_snapshot


class BaseCrawler(ABC):
    """合规爬虫基类"""

    platform: str = "base"
    BASE_URL: str = ""

    def __init__(self):
        self._client: httpx.Client | None = None
        self._last_request_time: float = 0
        self._request_count_this_hour: int = 0
        self._hour_start_time: float = time.time()
        self._robots_allowed: dict[str, bool] = {}  # 缓存 robots 检查结果

    # ---------- HTTP 客户端 ----------

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=COMPLIANCE_CONFIG["timeout"],
                follow_redirects=True,
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> dict:
        """构建合规请求头 — 明确标识爬虫身份"""
        return {
            "User-Agent": COMPLIANCE_CONFIG["user_agent"],
            "Accept": "text/html,application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "X-Usage-Purpose": COMPLIANCE_CONFIG["data_usage"],
        }

    # ---------- robots.txt 检查 ----------

    def check_robots(self, url: str = "") -> bool:
        """
        检查 robots.txt 是否允许爬取

        使用简化版解析：检查 User-agent: * 的 Disallow 规则
        """
        if not COMPLIANCE_CONFIG.get("check_robots_txt"):
            return True

        base_url = url or self.BASE_URL
        if not base_url:
            return True

        # 缓存检查
        robots_url = urljoin(base_url, "/robots.txt")
        if robots_url in self._robots_allowed:
            return self._robots_allowed[robots_url]

        try:
            resp = self._get_client().get(robots_url)
            if resp.status_code == 200:
                path = "/" + url.split("/", 3)[-1] if url else "/"
                allowed = self._parse_robots(resp.text, path)
                self._robots_allowed[robots_url] = allowed
                return allowed
        except Exception:
            # robots.txt 不可访问 → 保守允许 (仅限公开搜索页)
            pass

        self._robots_allowed[robots_url] = True
        return True

    @staticmethod
    def _parse_robots(robots_text: str, path: str) -> bool:
        """简化 robots.txt 解析"""
        import re
        user_agent_match = False
        for line in robots_text.splitlines():
            line = line.strip().lower()
            if line.startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                user_agent_match = agent == "*" or "competitiveanalysisbot" in agent
                continue
            if user_agent_match and line.startswith("disallow:"):
                rule = line.split(":", 1)[1].strip()
                if rule and path.startswith(rule):
                    return False
        return True

    # ---------- 速率限制 ----------

    def _rate_limit(self, url: str = ""):
        """多层速率限制"""
        # 1. 请求间隔
        delay_min, delay_max = COMPLIANCE_CONFIG["request_delay"]
        elapsed = time.time() - self._last_request_time
        if elapsed < delay_min:
            sleep_time = random.uniform(delay_min, delay_max) - elapsed
            time.sleep(sleep_time)

        # 2. 每小时上限
        max_per_hour = COMPLIANCE_CONFIG["max_requests_per_hour"]
        self._request_count_this_hour += 1
        if self._request_count_this_hour > max_per_hour:
            hour_elapsed = time.time() - self._hour_start_time
            if hour_elapsed < 3600:
                wait = 3600 - hour_elapsed
                print(f"[COMPLIANCE] 达到每小时请求上限，等待 {wait:.0f} 秒...")
                time.sleep(wait)
            self._request_count_this_hour = 0
            self._hour_start_time = time.time()

        self._last_request_time = time.time()

    # ---------- 请求封装 ----------

    def _request(self, url: str, params: dict | None = None) -> httpx.Response:
        """发送 GET 请求 (合规检查 + 重试)"""
        # robots 检查
        if not self.check_robots(url):
            raise PermissionError(f"robots.txt 禁止爬取: {url}")

        self._rate_limit(url)

        last_exception = None
        for attempt in range(COMPLIANCE_CONFIG["max_retries"]):
            try:
                resp = self._get_client().get(url, params=params)
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as e:
                last_exception = e
                wait = 2 ** attempt
                time.sleep(wait)
        raise last_exception  # type: ignore

    # ---------- 快照保存 ----------

    def _save_snapshot(
        self, task_id: int, html: str = "",
        api_response: dict | None = None, product_id: int | None = None,
    ) -> str:
        """保存原始快照 (溯源)"""
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
    def search_products(self, keyword: str, task_id: int, **kwargs) -> list[dict]:
        """搜索商品列表"""
        ...

    # ---------- 清理 ----------

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
