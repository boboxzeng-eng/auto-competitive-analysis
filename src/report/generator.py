"""
报告生成器

生成:
- 分析摘要文本
- Plotly 图表 JSON (便于 Streamlit 渲染)
- 结构化报告数据
"""

from datetime import datetime

from src.analysis.price import analyze_price_distribution
from src.analysis.market import analyze_market_overview
from src.storage.database import get_session
from src.storage.repository import (
    get_products_by_category,
    get_latest_completed_task,
)
from src.storage.models import Product


def generate_category_report(
    category_name: str,
    category_id: int,
    products: list[dict] | None = None,
) -> dict:
    """
    为指定品类生成完整分析报告

    Returns:
        {
            "meta": {...},         # 报告元信息
            "price_analysis": {...},  # 价格分析
            "market_analysis": {...}, # 市场分析
            "raw_data_count": int,    # 数据量
        }
    """
    if products is None:
        session = get_session()
        try:
            orm_products = get_products_by_category(session, category_id, limit=200)
            products = [p.to_dict() for p in orm_products]
        finally:
            session.close()

    report = {
        "meta": {
            "title": f"竞品分析报告 — {category_name}",
            "category": category_name,
            "generated_at": datetime.now().isoformat(),
            "data_count": len(products) if products else 0,
        },
        "price_analysis": analyze_price_distribution(products or []),
        "market_analysis": analyze_market_overview(products or []),
    }

    return report


def generate_comparison_report(
    category_name: str,
    jd_products: list[dict],
    tb_products: list[dict] | None = None,
) -> dict:
    """
    跨平台对比报告

    当有多个平台数据时，进行横向对比
    """
    report = {
        "meta": {
            "title": f"跨平台竞品对比 — {category_name}",
            "category": category_name,
            "generated_at": datetime.now().isoformat(),
        },
        "platforms": {},
    }

    # 京东
    report["platforms"]["jd"] = {
        "name": "京东",
        "product_count": len(jd_products),
        "price_analysis": analyze_price_distribution(jd_products),
        "market_analysis": analyze_market_overview(jd_products),
    }

    # 淘宝
    if tb_products:
        report["platforms"]["taobao"] = {
            "name": "淘宝",
            "product_count": len(tb_products),
            "price_analysis": analyze_price_distribution(tb_products),
            "market_analysis": analyze_market_overview(tb_products),
        }

    # 跨平台对比摘要
    report["cross_platform_summary"] = _compare_platforms(report["platforms"])

    return report


def _compare_platforms(platforms: dict) -> dict:
    """生成跨平台对比摘要"""
    if len(platforms) < 2:
        return {"note": "需要至少两个平台的数据才能对比"}

    comparison = {"price_comparison": {}, "count_comparison": {}}
    for key, data in platforms.items():
        comparison["count_comparison"][key] = data["product_count"]
        price = data["price_analysis"]
        if "mean_price" in price:
            comparison["price_comparison"][key] = price["mean_price"]

    return comparison
