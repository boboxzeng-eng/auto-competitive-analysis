"""
分析看板页面 — 可视化展示竞品分析结果
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.storage.database import get_session, init_db
from src.storage.repository import (
    get_all_categories, get_products_by_category,
    get_latest_completed_task,
)
from src.report.generator import (
    generate_category_report,
    render_html_report,
    export_report_to_file,
)


def render():
    st.title("📈 竞争分析看板")

    init_db()
    session = get_session()
    try:
        categories = get_all_categories(session)
        if not categories:
            st.info("还没有分析数据，请先在「🏠 品类选择」页启动一次分析。")
            return

        # 品类选择器
        cat_names = [c.name for c in categories]
        selected_name = st.selectbox(
            "选择品类查看报告",
            cat_names,
            key="dashboard_category",
        )

        if not selected_name:
            return

        # 获取数据
        category = next(c for c in categories if c.name == selected_name)
        products = get_products_by_category(session, category.id, limit=200)

        if not products:
            st.warning(f"「{selected_name}」还没有采集到商品数据")
            return

        product_dicts = [p.to_dict() for p in products]

        # 生成报告
        report = generate_category_report(
            category_name=selected_name,
            category_id=category.id,
            products=product_dicts,
        )

        # ---- 顶部操作栏 ----
        col_title, col_export = st.columns([3, 1])
        with col_title:
            st.subheader(f"📊 {report['meta']['title']}")
            st.caption(
                f"生成时间: {report['meta']['generated_at']} | "
                f"数据量: {report['meta']['data_count']} 件商品"
            )
        with col_export:
            _render_export_button(report, product_dicts, selected_name, category.id)

        # ---- KPI 卡片 ----
        _render_kpi_cards(report)

        st.markdown("---")

        # ---- 图表区 ----
        col1, col2 = st.columns(2)

        with col1:
            _render_price_chart(report)

        with col2:
            _render_brand_chart(report)

        st.markdown("---")

        # ---- 商品列表 ----
        _render_product_table(product_dicts)

    finally:
        session.close()


def _render_export_button(report: dict, products: list[dict], category_name: str, category_id: int):
    """渲染 HTML 导出按钮"""
    st.markdown("")  # 对齐间距

    if st.button("📥 导出 HTML 报告", type="primary", use_container_width=True):
        with st.spinner("正在生成 HTML 报告..."):
            try:
                html = render_html_report(report, products)
                st.download_button(
                    label="⬇️ 下载 HTML 报告",
                    data=html,
                    file_name=f"report_{category_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.html",
                    mime="text/html",
                )
                st.success("✅ 报告已生成，点击上方按钮下载")
            except Exception as e:
                st.error(f"生成失败: {e}")


def _render_kpi_cards(report: dict):
    """KPI 概览卡片"""
    price = report.get("price_analysis", {})

    cols = st.columns(5)
    metrics = [
        ("商品总数", f"{report['meta']['data_count']} 件"),
        ("最低价", f"¥{price.get('min_price', 'N/A')}"),
        ("平均价", f"¥{price.get('mean_price', 'N/A')}"),
        ("最高价", f"¥{price.get('max_price', 'N/A')}"),
        ("中位数", f"¥{price.get('median_price', 'N/A')}"),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            st.metric(label=label, value=value)


def _render_price_chart(report: dict):
    """价格分布图表"""
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


def _render_brand_chart(report: dict):
    """品牌分布图表"""
    market = report.get("market_analysis", {})
    brands = market.get("brand_distribution", [])

    if not brands:
        st.info("暂无品牌数据")
        return

    st.subheader("🏷️ 品牌分布 Top10")

    df_brands = pd.DataFrame(brands, columns=["brand", "count"])
    fig = px.pie(
        df_brands, names="brand", values="count",
        title="品牌市场份额",
        hole=0.4,
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_product_table(products: list[dict]):
    """商品明细表格"""
    st.subheader("📋 商品明细")

    if not products:
        st.info("暂无商品数据")
        return

    df = pd.DataFrame(products)
    show_cols = {
        "title": "商品名称",
        "price": "价格 (¥)",
        "shop_name": "店铺",
        "brand": "品牌",
        "sales_volume": "销量",
        "platform": "平台",
        "url": "链接",
    }
    cols = [c for c in show_cols if c in df.columns]
    df_show = df[cols].rename(columns=show_cols)

    if "价格 (¥)" in df_show.columns:
        df_show["价格 (¥)"] = df_show["价格 (¥)"].apply(
            lambda x: f"¥{x:.2f}" if pd.notna(x) else "-"
        )

    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "链接": st.column_config.LinkColumn("链接"),
        },
    )
