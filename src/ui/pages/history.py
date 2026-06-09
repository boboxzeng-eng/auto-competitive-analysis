"""
历史溯源页面 — 查看历史分析记录和原始数据快照
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from src.storage.database import get_session, init_db
from src.storage.repository import (
    get_all_categories, get_tasks_by_category,
    get_products_by_task, get_snapshots_by_task,
)


def render():
    st.title("📋 历史溯源")

    init_db()
    session = get_session()
    try:
        categories = get_all_categories(session)
        if not categories:
            st.info("还没有分析记录")
            return

        # 品类选择
        cat_names = [c.name for c in categories]
        selected_name = st.selectbox(
            "选择品类查看历史",
            cat_names,
            key="history_category",
        )
        category = next(c for c in categories if c.name == selected_name)

        # 任务列表
        tasks = get_tasks_by_category(session, category.id)
        if not tasks:
            st.info(f"「{selected_name}」还没有分析任务")
            return

        _render_task_history(session, tasks, category.name)

    finally:
        session.close()


def _render_task_history(session, tasks, category_name: str):
    """渲染任务历史"""
    st.subheader(f"📁 {category_name} — 采集历史")

    for task in tasks:
        status_icon = {
            "completed": "✅",
            "failed": "❌",
            "running": "🔄",
            "pending": "⏳",
        }.get(task.status, "❓")

        with st.expander(
            f"{status_icon} [{task.platform.upper()}] {task.keyword_used} "
            f"— {task.product_count} 件商品 "
            f"({task.finished_at.strftime('%m-%d %H:%M') if task.finished_at else '进行中'})",
            expanded=False,
        ):
            # 任务元数据
            st.markdown(f"""
            | 属性 | 值 |
            |------|-----|
            | 平台 | {task.platform} |
            | 关键词 | {task.keyword_used} |
            | 状态 | {task.status} |
            | 商品数 | {task.product_count} |
            | 开始时间 | {task.started_at} |
            | 结束时间 | {task.finished_at} |
            """)

            if task.error_message:
                st.error(f"错误信息: {task.error_message}")

            # 查看商品
            col1, col2 = st.columns(2)

            with col1:
                if st.button(f"📦 查看商品数据", key=f"products_{task.id}"):
                    products = get_products_by_task(session, task.id)
                    if products:
                        df = pd.DataFrame([p.to_dict() for p in products])
                        st.dataframe(
                            df[["title", "price", "shop_name", "brand"]],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("无商品数据")

            with col2:
                if st.button(f"🔍 查看原始快照", key=f"snapshots_{task.id}"):
                    snapshots = get_snapshots_by_task(session, task.id)
                    if snapshots:
                        st.info(f"共 {len(snapshots)} 条原始快照")
                        for snap in snapshots[:5]:  # 最多显示5条
                            with st.container():
                                st.caption(
                                    f"快照 ID: {snap.id} | "
                                    f"时间: {snap.crawled_at.strftime('%Y-%m-%d %H:%M:%S')}"
                                )
                                tab1, tab2 = st.tabs(["HTML", "JSON"])
                                with tab1:
                                    if snap.raw_html:
                                        html_preview = snap.raw_html[:2000]
                                        st.code(html_preview, language="html")
                                    else:
                                        st.info("无 HTML 快照")
                                with tab2:
                                    if snap.raw_json:
                                        st.json(snap.raw_json)
                                    else:
                                        st.info("无 JSON 快照")
                    else:
                        st.info("无原始快照记录")
