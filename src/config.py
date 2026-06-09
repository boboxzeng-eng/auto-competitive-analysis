"""
配置管理模块
"""

import os
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

# 数据目录
DATA_DIR = ROOT_DIR / "data"

# 数据库配置
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATA_DIR}/competitive_analysis.db"
)

# ==================== 爬虫合规配置 ====================

COMPLIANCE_CONFIG = {
    # 爬虫身份标识 (合规 — 明确声明身份)
    "user_agent": (
        "CompetitiveAnalysisBot/1.0 "
        "(Personal Research; +https://github.com/boboxzeng-eng/auto-competitive-analysis)"
    ),
    "request_delay": (3, 6),        # 请求间隔 (秒) — 更保守
    "max_retries": 3,
    "timeout": 30,                  # 请求超时 (秒)
    "max_requests_per_hour": 200,   # 每小时请求上限
    "max_products_per_search": 40,  # 每次搜索最大商品数
    "check_robots_txt": True,       # 是否检查 robots.txt
    "respect_crawl_delay": True,    # 遵守 Crawl-Delay
    "data_usage": (
        "仅供个人竞品分析使用，不用于商业目的。"
        "仅采集公开搜索列表页数据。"
    ),
}

# 兼容旧配置
CRAWL_CONFIG = COMPLIANCE_CONFIG

# ==================== 支持的平台 ====================

SUPPORTED_PLATFORMS = {
    "jd": {"name": "京东", "enabled": True, "base_url": "https://www.jd.com"},
    "taobao": {"name": "淘宝", "enabled": False, "base_url": "https://www.taobao.com"},
    "pdd": {"name": "拼多多", "enabled": False, "base_url": "https://www.pinduoduo.com"},
    "douyin": {"name": "抖音电商", "enabled": False, "base_url": "https://www.douyin.com"},
}

# ==================== 竞品分析配置 ====================

# 品牌竞品关系表 — 哪些品牌互为竞品
BRAND_COMPETITOR_MAP = {
    "华为": ["荣耀", "小米", "OPPO", "vivo", "三星", "苹果"],
    "荣耀": ["华为", "小米", "OPPO", "vivo"],
    "小米": ["华为", "荣耀", "OPPO", "vivo", "三星", "苹果"],
    "OPPO": ["华为", "荣耀", "小米", "vivo", "三星"],
    "vivo": ["华为", "荣耀", "小米", "OPPO", "三星"],
    "苹果": ["华为", "小米", "三星", "OPPO", "vivo"],
    "三星": ["华为", "小米", "苹果", "OPPO", "vivo"],
    # 笔记本电脑
    "联想": ["戴尔", "惠普", "华硕", "华为", "苹果"],
    "戴尔": ["联想", "惠普", "华硕", "苹果"],
    "惠普": ["联想", "戴尔", "华硕", "苹果"],
    "华硕": ["联想", "戴尔", "惠普", "华为", "苹果"],
    # 家电
    "海尔": ["美的", "格力", "海信", "TCL"],
    "美的": ["海尔", "格力", "海信", "TCL"],
    "格力": ["海尔", "美的", "海信", "TCL"],
}

# 预置品类及其竞品关键词
PRESET_CATEGORIES = {
    "手机": {
        "keywords": ["手机", "智能手机", "5G手机"],
        "specs": ["屏幕尺寸", "CPU", "内存", "存储", "摄像头", "电池"],
        "price_range": (500, 15000),
    },
    "耳机": {
        "keywords": ["耳机", "蓝牙耳机", "降噪耳机"],
        "specs": ["类型", "连接方式", "降噪", "续航"],
        "price_range": (50, 3000),
    },
    "笔记本电脑": {
        "keywords": ["笔记本电脑", "笔记本", "轻薄本"],
        "specs": ["屏幕尺寸", "CPU", "内存", "硬盘", "显卡"],
        "price_range": (2000, 20000),
    },
    "护肤品": {
        "keywords": ["护肤品", "面霜", "精华液"],
        "specs": ["功效", "成分", "容量", "适用肤质"],
        "price_range": (50, 3000),
    },
    "扫地机器人": {
        "keywords": ["扫地机器人", "扫拖一体机"],
        "specs": ["导航方式", "吸力", "水箱容量", "续航"],
        "price_range": (500, 8000),
    },
}

# 默认竞品匹配权重
DEFAULT_MATCH_WEIGHTS = {
    "price_similarity": 0.40,   # 价格接近度
    "category_match": 0.30,     # 品类匹配度
    "brand_competition": 0.20,  # 品牌竞争度
    "spec_similarity": 0.10,    # 规格相似度
}

# 竞品最低得分阈值 (低于此值不算竞品)
COMPETITOR_SCORE_THRESHOLD = 0.45
