"""
品类选择页面 — 用户选择商品品类并触发爬取任务
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from src.config import PRESET_CATEGORIES, SUPPORTED_PLATFORMS, CRAWL_CONFIG
from src.storage.database import get_session, init_db
from src.storage.repository import (
    create_category, get_all_categories, get_category_by_name,
    create_crawl_task, update_task_status, save_products,
    get_products_by_task, get_tasks_by_category,
)
from src.storage.models import TaskStatus
from src.crawlers.jd import JDCrawler


def render():
    st.title("🏠 选择分析品类")

    init_db()

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("📦 品类配置")
        _render_category_selector()

    with col2:
        st.subheader("📋 任务状态")
        _render_task_panel()


def _render_category_selector():
    """品类选择区域"""
    preset_names = list(PRESET_CATEGORIES.keys())
    selected_preset = st.selectbox("选择品类", preset_names)

    if selected_preset:
        keywords = PRESET_CATEGORIES[selected_preset]
        st.markdown(f"**预置关键词**: `{'`, `'.join(keywords)}`")

        custom_keyword = st.text_input(
            "自定义关键词",
            placeholder="输入自定义搜索词 (留空使用预置关键词)",
        )

        # 爬取参数
        with st.expander("⚙️ 爬取参数", expanded=False):
            max_pages = st.slider(
                "最大翻页数",
                min_value=1,
                max_value=5,
                value=2,
                help="每页约 30 件商品。页数越多耗时越长，反爬风险越高。",
            )
            headless = st.checkbox("无头模式", value=True, help="不显示浏览器窗口")

        # 平台选择
        st.markdown("**目标平台**:")
        platform_cols = st.columns(2)
        selected_platforms = {}
        for i, (key, info) in enumerate(SUPPORTED_PLATFORMS.items()):
            with platform_cols[i % 2]:
                disabled = not info["enabled"]
                selected_platforms[key] = st.checkbox(
                    f"{'🔒 ' if disabled else ''}{info['name']}",
                    value=info["enabled"],
                    disabled=disabled,
                    help=f"{'暂未开放' if disabled else '已就绪'}",
                )

        # 启动按钮
        do_keyword = custom_keyword.strip() if custom_keyword.strip() else keywords[0]
        if st.button("🚀 开始分析", type="primary", use_container_width=True):
            if not any(selected_platforms.values()):
                st.error("请至少选择一个平台")
                return

            with st.spinner(f"正在采集「{do_keyword}」数据 (最多 {max_pages} 页)..."):
                result = _run_crawl(
                    category_name=selected_preset,
                    keyword=do_keyword,
                    platforms=[k for k, v in selected_platforms.items() if v],
                    max_pages=max_pages,
                    headless=headless,
                )

            if result["total"] > 0:
                st.success(
                    f"✅ 采集完成! 共获取 {result['total']} 件商品。"
                    f"请切换到「📈 分析看板」查看结果"
                )
            else:
                st.warning("⚠️ 未获取到商品数据，请尝试其他关键词或稍后重试。")


def _run_crawl(
    category_name: str,
    keyword: str,
    platforms: list[str],
    max_pages: int = 2,
    headless: bool = True,
) -> dict:
    """执行爬取任务"""
    session = get_session()
    all_products = []

    try:
        category = get_category_by_name(session, category_name)
        if not category:
            keywords = PRESET_CATEGORIES.get(category_name, [keyword])
            category = create_category(session, category_name, keywords)
        category_id = category.id

        for platform in platforms:
            task = create_crawl_task(session, category_id, platform, keyword)
            update_task_status(session, task.id, TaskStatus.RUNNING)

            try:
                if platform == "jd":
                    crawler = JDCrawler(headless=headless)
                    products = crawler.search_products(
                        keyword=keyword,
                        task_id=task.id,
                        max_pages=max_pages,
                    )
                    crawler.close()
                else:
                    products = []

                if products:
                    for p in products:
                        p["category_id"] = category_id
                    save_products(session, products, task.id)

                update_task_status(
                    session, task.id, TaskStatus.COMPLETED,
                    product_count=len(products),
                )
                all_products.extend(products)

            except Exception as e:
                update_task_status(
                    session, task.id, TaskStatus.FAILED,
                    error_message=str(e),
                )
                st.warning(f"[{platform}] 采集出错: {e}")

        st.session_state["last_category_id"] = category_id
        st.session_state["last_category_name"] = category_name
        st.session_state["last_product_count"] = len(all_products)

    finally:
        session.close()

    return {"total": len(all_products)}


def _render_task_panel():
    """任务历史面板"""
    session = get_session()
    try:
        categories = get_all_categories(session)
        if not categories:
            st.info("还没有分析记录，选择一个品类开始吧 👈")
            return

        for cat in categories:
            with st.expander(f"📁 {cat.name} (ID: {cat.id})", expanded=False):
                st.caption(f"关键词: `{'`, `'.join(cat.keywords)}`")
                st.caption(f"创建时间: {cat.created_at.strftime('%Y-%m-%d %H:%M')}")

                tasks = get_tasks_by_category(session, cat.id)
                if tasks:
                    rows = []
                    for t in tasks:
                        status_icon = {
                            "completed": "✅", "failed": "❌",
                            "running": "🔄", "pending": "⏳",
                        }.get(t.status, "❓")
                        rows.append({
                            "状态": f"{status_icon} {t.status}",
                            "平台": t.platform,
                            "关键词": t.keyword_used,
                            "商品数": t.product_count,
                            "时间": (
                                t.finished_at.strftime("%m-%d %H:%M")
                                if t.finished_at else "-"
                            ),
                        })
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )
    finally:
        session.close()
