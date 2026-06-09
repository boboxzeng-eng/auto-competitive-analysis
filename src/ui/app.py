"""
自动化竞分析 — Streamlit 主入口

启动方式:
    streamlit run src/ui/app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(
    page_title="自动化竞分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 侧边导航
st.sidebar.title("📊 自动化竞分析")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "导航",
    ["🎯 竞品工作台", "📈 分析看板", "📋 历史溯源"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "**合规声明**: 本工具仅采集电商平台公开搜索列表页数据，"
    "供个人竞品分析使用，不用于商业目的。"
    "遵守 robots.txt 规范，明确标识爬虫身份。"
)

# 路由
if page == "🎯 竞品工作台":
    from src.ui.pages import workbench
    workbench.render()

elif page == "📈 分析看板":
    from src.ui.pages import dashboard
    dashboard.render()

elif page == "📋 历史溯源":
    from src.ui.pages import history
    history.render()
