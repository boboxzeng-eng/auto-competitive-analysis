"""
报告生成器

支持:
- 分析报告数据结构生成
- Jinja2 HTML 模板渲染 (完整离线报告)
- 跨平台对比报告
"""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.analysis.price import analyze_price_distribution
from src.analysis.market import analyze_market_overview
from src.storage.database import get_session
from src.storage.repository import get_products_by_category

# 模板目录
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    """获取 Jinja2 环境"""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )


def generate_category_report(
    category_name: str,
    category_id: int,
    products: list[dict] | None = None,
) -> dict:
    """为指定品类生成完整分析报告"""
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
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_count": len(products) if products else 0,
            "data_source": "京东 (JD.com)",
            "compliance_note": (
                "本报告数据来源于电商平台公开搜索列表页，"
                "仅供个人竞品分析使用。采集过程遵守 robots.txt，"
                "明确标识爬虫身份，所有数据可溯源。"
            ),
        },
        "price_analysis": analyze_price_distribution(products or []),
        "market_analysis": analyze_market_overview(products or []),
    }

    return report


def render_html_report(
    report: dict,
    products: list[dict],
    output_path: str | None = None,
) -> str:
    """
    将报告渲染为 HTML 文件

    Args:
        report: generate_category_report 返回的报告数据
        products: 商品列表 (含溯源链接)
        output_path: 输出文件路径 (可选)

    Returns:
        HTML 字符串
    """
    env = _get_jinja_env()
    template = env.get_template("report.html")

    html = template.render(
        report=report,
        products=products,
    )

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return str(path.absolute())

    return html


def export_report_to_file(
    category_name: str,
    category_id: int,
    products: list[dict] | None = None,
    output_dir: str | None = None,
) -> str:
    """
    一键导出: 生成报告 + 渲染 HTML + 保存文件

    Returns:
        输出文件路径
    """
    report = generate_category_report(category_name, category_id, products)

    if output_dir is None:
        from src.config import DATA_DIR
        output_dir = str(DATA_DIR / "reports")
    else:
        output_dir = str(output_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{category_name}_{timestamp}.html"
    output_path = str(Path(output_dir) / filename)

    return render_html_report(report, products or [], output_path)


def generate_comparison_report(
    category_name: str,
    jd_products: list[dict],
    tb_products: list[dict] | None = None,
) -> dict:
    """跨平台对比报告"""
    report = {
        "meta": {
            "title": f"跨平台竞品对比 — {category_name}",
            "category": category_name,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "platforms": {},
    }

    report["platforms"]["jd"] = {
        "name": "京东",
        "product_count": len(jd_products),
        "price_analysis": analyze_price_distribution(jd_products),
        "market_analysis": analyze_market_overview(jd_products),
    }

    if tb_products:
        report["platforms"]["taobao"] = {
            "name": "淘宝",
            "product_count": len(tb_products),
            "price_analysis": analyze_price_distribution(tb_products),
            "market_analysis": analyze_market_overview(tb_products),
        }

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
