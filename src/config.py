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

# 爬虫配置
CRAWL_CONFIG = {
    "request_delay": (2, 5),      # 请求间隔 (秒)
    "max_retries": 3,              # 最大重试次数
    "timeout": 30,                 # 请求超时 (秒)
    "max_products_per_search": 40, # 每次搜索最大商品数
    "user_agent_rotation": True,   # 是否轮换 UA
}

# 支持的平台
SUPPORTED_PLATFORMS = {
    "jd": {"name": "京东", "enabled": True},
    "taobao": {"name": "淘宝", "enabled": False},
    "pdd": {"name": "拼多多", "enabled": False},
    "douyin": {"name": "抖音电商", "enabled": False},
}

# 预置品类关键词
PRESET_CATEGORIES = {
    "手机": ["手机", "智能手机", "5G手机"],
    "耳机": ["耳机", "蓝牙耳机", "降噪耳机"],
    "笔记本电脑": ["笔记本电脑", "笔记本", "轻薄本"],
    "护肤品": ["护肤品", "面霜", "精华液"],
    "扫地机器人": ["扫地机器人", "扫拖一体机"],
}
