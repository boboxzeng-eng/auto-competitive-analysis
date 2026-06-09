"""
自动化竞分析 — Streamlit 主入口

启动方式:
    cd auto-competitive-analysis
    streamlit run src/ui/app.py
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

# 页面配置
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
    ["🏠 品类选择", "📈 分析看板", "📋 历史溯源"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**数据来源**: 京东、淘宝、拼多多等电商平台\n\n"
    "**数据可溯源**: 所有分析数据均保留原始采集快照"
)

# 页面路由
if page == "🏠 品类选择":
    from src.ui.pages import category
    category.render()

elif page == "📈 分析看板":
    from src.ui.pages import dashboard
    dashboard.render()

elif page == "📋 历史溯源":
    from src.ui.pages import history
    history.render()
