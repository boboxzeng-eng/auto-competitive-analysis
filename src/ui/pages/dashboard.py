"""
分析看板页面 — 竞品分析结果可视化
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px

from src.storage.database import get_session, init_db
from src.storage.repository import (
    get_all_categories, get_products_by_category,
    get_competitors_by_task,
)
from src.report.generator import (
    generate_category_report,
    render_html_report,
)


def render():
    st.title("📈 竞争分析看板")

    init_db()
    session = get_session()
    try:
        categories = get_all_categories(session)
        if not categories:
            st.info("还没有分析数据，请先在「🎯 竞品工作台」页启动分析。")
            return

        cat_names = [c.name for c in categories]
        selected_name = st.selectbox("选择品类查看报告", cat_names)
        if not selected_name:
            return

        category = next(c for c in categories if c.name == selected_name)
        products = get_products_by_category(session, category.id, limit=200)

        if not products:
            st.warning(f"「{selected_name}」还没有采集到商品数据")
            return

        product_dicts = [p.to_dict() for p in products]

        # 竞品筛选
        competitors_only = st.toggle("仅显示竞品", value=True)
        if competitors_only:
            display_products = [p for p in product_dicts if p.get("is_competitor")]
        else:
            display_products = product_dicts

        report = generate_category_report(
            category_name=selected_name,
            category_id=category.id,
            products=product_dicts,
        )

        # ---- 顶部操作栏 ----
        col_title, col_export = st.columns([3, 1])
        with col_title:
            comp_count = sum(1 for p in product_dicts if p.get("is_competitor"))
            st.subheader(f"📊 {report['meta']['title']}")
            st.caption(
                f"商品总数: {len(product_dicts)} | "
                f"🎯 竞品: {comp_count} 件 | "
                f"生成时间: {report['meta']['generated_at']}"
            )
        with col_export:
            if st.button("📥 导出 HTML 报告", type="primary", use_container_width=True):
                with st.spinner("正在生成 HTML 报告..."):
                    html = render_html_report(report, product_dicts)
                    st.download_button(
                        label="⬇️ 下载 HTML 报告",
                        data=html,
                        file_name=f"report_{selected_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.html",
                        mime="text/html",
                    )

        # ---- KPI 卡片 ----
        _render_kpi_cards(report, comp_count)

        st.markdown("---")

        # ---- 图表区 ----
        col1, col2 = st.columns(2)
        with col1:
            _render_price_chart(report)
        with col2:
            _render_competitor_score_chart(display_products)

        st.markdown("---")

        # ---- 商品列表 ----
        _render_product_table(display_products)

    finally:
        session.close()


def _render_kpi_cards(report: dict, comp_count: int):
    price = report.get("price_analysis", {})
    cols = st.columns(6)
    metrics = [
        ("商品总数", f"{report['meta']['data_count']} 件"),
        ("🎯 竞品数", f"{comp_count} 件"),
        ("最低价", f"¥{price.get('min_price', 'N/A')}"),
        ("平均价", f"¥{price.get('mean_price', 'N/A')}"),
        ("最高价", f"¥{price.get('max_price', 'N/A')}"),
        ("中位数", f"¥{price.get('median_price', 'N/A')}"),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            st.metric(label=label, value=value)


def _render_price_chart(report: dict):
    price = report.get("price_analysis", {})
    ranges = price.get("price_ranges", [])
    if not ranges:
        st.info("暂无价格数据")
        return

    st.subheader("💰 价格区间分布")
    df_ranges = pd.DataFrame(ranges)
    fig = px.bar(
        df_ranges, x="range", y="count",
        title="各价格区间商品数量",
        labels={"range": "价格区间", "count": "商品数"},
        color="count",
        color_continuous_scale="Blues",
    )
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, use_container_width=True)


def _render_competitor_score_chart(products: list[dict]):
    """竞品得分分布"""
    st.subheader("🎯 竞品得分分布")

    scored = [p for p in products if p.get("competitor_score") is not None]
    if not scored:
        st.info("暂无竞品得分数据")
        return

    df = pd.DataFrame(scored)
    df = df.sort_values("competitor_score", ascending=True)

    # 给每个商品截短标题
    df["short_title"] = df["title"].apply(lambda x: x[:25] + "..." if len(x) > 25 else x)

    fig = px.bar(
        df.tail(15),  # Top 15
        x="competitor_score",
        y="short_title",
        orientation="h",
        title="竞品得分 Top 15",
        labels={"competitor_score": "竞品得分", "short_title": ""},
        color="competitor_score",
        color_continuous_scale="RdYlGn",
        range_color=[0, 1],
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)


def _render_product_table(products: list[dict]):
    st.subheader("📋 商品明细")

    if not products:
        st.info("暂无商品数据")
        return

    df = pd.DataFrame(products)
    show_cols = {
        "title": "商品名称",
        "price": "价格 (¥)",
        "competitor_score": "竞品得分",
        "brand": "品牌",
        "shop_name": "店铺",
        "sales_volume": "销量",
        "platform": "平台",
        "url": "链接",
    }
    cols = [c for c in show_cols if c in df.columns]
    df_show = df[cols].rename(columns=show_cols).copy()

    if "价格 (¥)" in df_show.columns:
        df_show["价格 (¥)"] = df_show["价格 (¥)"].apply(
            lambda x: f"¥{x:.2f}" if pd.notna(x) else "-"
        )
    if "竞品得分" in df_show.columns:
        df_show["竞品得分"] = df_show["竞品得分"].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "-"
        )

    st.dataframe(
        df_show.sort_values("竞品得分", ascending=False) if "竞品得分" in df_show.columns else df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "链接": st.column_config.LinkColumn("链接"),
        },
    )
