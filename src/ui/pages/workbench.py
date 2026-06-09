"""
竞品分析工作台 — 对标产品定义 + 竞品匹配规则 + 启动分析
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from src.config import (
    PRESET_CATEGORIES, SUPPORTED_PLATFORMS,
    DEFAULT_MATCH_WEIGHTS, BRAND_COMPETITOR_MAP,
)
from src.storage.database import get_session, init_db
from src.storage.repository import (
    create_category, get_all_categories, get_category_by_name,
    create_crawl_task, update_task_status, save_products,
    get_tasks_by_profile, create_profile, get_all_profiles,
)
from src.storage.models import TaskStatus
from src.crawlers.jd import JDCrawler
from src.analysis.competitor import CompetitiveMatcher


def render():
    st.title("🎯 竞品分析工作台")

    init_db()

    col1, col2 = st.columns([3, 2])

    with col1:
        _render_profile_form()

    with col2:
        _render_history_panel()


def _render_profile_form():
    """对标产品定义表单"""
    st.subheader("📱 对标产品定义")

    # 品类 → 动态调整规格选项
    preset_names = list(PRESET_CATEGORIES.keys())
    selected_category = st.selectbox("品类", preset_names)

    cat_info = PRESET_CATEGORIES.get(selected_category, {})
    if isinstance(cat_info, dict):
        cat_specs = cat_info.get("specs", [])
        cat_keywords = cat_info.get("keywords", [])
        default_price = cat_info.get("price_range", (0, 99999))
    else:
        cat_specs = []
        cat_keywords = cat_info
        default_price = (0, 99999)

    with st.container(border=True):
        col_a, col_b = st.columns(2)

        with col_a:
            product_name = st.text_input(
                "产品名称",
                placeholder="例如: 小米 16 Ultra",
                help="输入你对标的具体产品名称",
            )

        with col_b:
            brand = st.text_input(
                "品牌",
                placeholder="例如: 小米",
                help="输入品牌名称，用于匹配竞品品牌",
            )
            # 自动补全提示
            if brand and brand in BRAND_COMPETITOR_MAP:
                comps = BRAND_COMPETITOR_MAP[brand]
                st.caption(f"竞品品牌: {'、'.join(comps[:6])}")

        # 价格区间
        st.markdown("**目标价格区间 (元)**")
        pc1, pc2, pc3 = st.columns([1, 1, 2])
        with pc1:
            price_min = st.number_input(
                "最低价", value=float(default_price[0]),
                min_value=0.0, step=100.0, key="price_min",
            )
        with pc2:
            price_max = st.number_input(
                "最高价", value=float(default_price[1]),
                min_value=0.0, step=100.0, key="price_max",
            )
        with pc3:
            st.caption(f"搜索关键词: `{'`, `'.join(cat_keywords[:3])}`")

        # 核心规格
        st.markdown("**核心规格** (可选)")
        spec_cols = st.columns(min(4, max(2, len(cat_specs))))
        specs = {}
        for i, spec_name in enumerate(cat_specs[:8]):
            with spec_cols[i % 4]:
                specs[spec_name] = st.text_input(
                    spec_name,
                    placeholder="如: 6.7英寸",
                    key=f"spec_{spec_name}",
                )
        specs = {k: v for k, v in specs.items() if v.strip()}

    # 搜索关键词
    search_keyword = st.text_input(
        "自定义搜索关键词",
        placeholder=f"留空使用: {cat_keywords[0]}",
        help="可以填写更具体的搜索词以精准定位竞品",
    )

    # 竞品匹配权重
    with st.expander("🎯 竞品匹配权重", expanded=False):
        st.caption("调整各维度权重，总和为 100%")
        w1, w2, w3, w4 = st.columns(4)
        with w1:
            w_price = st.slider("价格接近度", 0, 100, 40, 5, key="w_price") / 100
        with w2:
            w_category = st.slider("品类匹配度", 0, 100, 30, 5, key="w_cat") / 100
        with w3:
            w_brand = st.slider("品牌竞争度", 0, 100, 20, 5, key="w_brand") / 100
        with w4:
            w_spec = st.slider("规格相似度", 0, 100, 10, 5, key="w_spec") / 100

        weights = {
            "price_similarity": w_price,
            "category_match": w_category,
            "brand_competition": w_brand,
            "spec_similarity": w_spec,
        }

        # 竞品阈值
        threshold = st.slider(
            "竞品识别阈值", 0.0, 1.0, 0.45, 0.05,
            help="综合得分高于此值才视为竞品",
        )

    # 平台选择
    st.markdown("**目标平台**")
    plat_cols = st.columns(4)
    selected_platforms = {}
    for i, (key, info) in enumerate(SUPPORTED_PLATFORMS.items()):
        with plat_cols[i]:
            disabled = not info["enabled"]
            selected_platforms[key] = st.checkbox(
                f"{'🔒 ' if disabled else ''}{info['name']}",
                value=info["enabled"],
                disabled=disabled,
            )

    # 爬取参数
    with st.expander("⚙️ 爬取参数", expanded=False):
        max_pages = st.slider("最大翻页数", 1, 5, 2)
        headless = st.checkbox("无头模式", value=True)

    # 启动按钮
    do_keyword = search_keyword.strip() if search_keyword.strip() else cat_keywords[0]

    if st.button("🚀 开始竞品分析", type="primary", use_container_width=True):
        if not product_name.strip():
            st.error("请输入对标产品名称")
            return

        if not any(selected_platforms.values()):
            st.error("请至少选择一个平台")
            return

        # 构建竞品画像
        profile_data = {
            "product_name": product_name.strip(),
            "brand": brand.strip(),
            "category": selected_category,
            "price_min": price_min,
            "price_max": price_max,
            "key_specs": specs,
            "match_weights": weights,
        }

        with st.spinner(f"正在分析「{product_name}」的竞品..."):
            result = _run_competitive_analysis(
                profile_data=profile_data,
                keyword=do_keyword,
                platforms=[k for k, v in selected_platforms.items() if v],
                max_pages=max_pages,
                headless=headless,
                threshold=threshold,
            )

        if result["total"] > 0:
            comp_count = result["competitors"]
            st.success(
                f"✅ 分析完成! 采集 {result['total']} 件商品，"
                f"识别出 {comp_count} 件竞品。"
                f"请切换到「📈 分析看板」查看结果"
            )
        else:
            st.warning("⚠️ 未获取到商品数据，请调整搜索条件后重试。")


def _run_competitive_analysis(
    profile_data: dict,
    keyword: str,
    platforms: list[str],
    max_pages: int = 2,
    headless: bool = True,
    threshold: float = 0.45,
) -> dict:
    """执行竞品分析全流程"""
    session = get_session()
    all_products = []

    try:
        # 1. 保存竞品画像
        profile = create_profile(
            session=session,
            name=f"{profile_data['product_name']} 竞品分析",
            product_name=profile_data["product_name"],
            brand=profile_data["brand"],
            category=profile_data["category"],
            price_min=profile_data["price_min"],
            price_max=profile_data["price_max"],
            specs=profile_data.get("key_specs"),
            match_weights=profile_data.get("match_weights"),
            platforms=platforms,
        )

        # 2. 创建品类 (兼容旧逻辑)
        category = get_category_by_name(session, profile_data["category"])
        if not category:
            category = create_category(
                session, profile_data["category"],
                [keyword],
            )

        # 3. 为每个平台爬取
        for platform in platforms:
            task = create_crawl_task(
                session=session,
                platform=platform,
                keyword_used=keyword,
                category_id=category.id,
                profile_id=profile.id,
                profile_json=profile_data,
            )
            update_task_status(session, task.id, TaskStatus.RUNNING)

            try:
                if platform == "jd":
                    crawler = JDCrawler(headless=headless)
                    products = crawler.search_products(
                        keyword=keyword,
                        task_id=task.id,
                        price_min=profile_data["price_min"],
                        price_max=profile_data["price_max"],
                        max_pages=max_pages,
                    )
                    crawler.close()
                else:
                    products = []

                # 4. 竞品匹配
                if products:
                    matcher = CompetitiveMatcher({
                        **profile_data,
                        "match_weights": profile_data.get("match_weights", {}),
                    })
                    matcher.threshold = threshold
                    products = matcher.evaluate_batch(products)

                    for p in products:
                        p["category_id"] = category.id
                    save_products(session, products, task.id)

                competitor_count = sum(1 for p in products if p.get("is_competitor"))
                update_task_status(
                    session, task.id, TaskStatus.COMPLETED,
                    product_count=len(products),
                    competitor_count=competitor_count,
                )
                all_products.extend(products)

            except Exception as e:
                update_task_status(
                    session, task.id, TaskStatus.FAILED,
                    error_message=str(e),
                )
                st.warning(f"[{platform}] 采集出错: {e}")

        st.session_state["last_category_id"] = category.id
        st.session_state["last_category_name"] = profile_data["category"]
        st.session_state["last_product_count"] = len(all_products)

    finally:
        session.close()

    return {
        "total": len(all_products),
        "competitors": sum(1 for p in all_products if p.get("is_competitor")),
    }


def _render_history_panel():
    """历史画像面板"""
    session = get_session()
    try:
        profiles = get_all_profiles(session)
        if not profiles:
            st.info("还没有竞品分析记录，在左侧填写对标产品信息开始 👈")
            return

        st.subheader("📋 历史分析")
        for prof in profiles[:10]:
            with st.expander(
                f"📁 {prof.name}",
                expanded=False,
            ):
                st.caption(f"产品: {prof.product_name}")
                st.caption(f"品牌: {prof.brand or '未指定'}")
                st.caption(f"品类: {prof.category}")
                st.caption(f"价格: ¥{prof.price_min or 0} - ¥{prof.price_max or '∞'}")
                st.caption(f"创建: {prof.created_at.strftime('%Y-%m-%d %H:%M')}")

                tasks = get_tasks_by_profile(session, prof.id)
                if tasks:
                    rows = [{
                        "平台": t.platform,
                        "关键词": t.keyword_used,
                        "商品数": t.product_count,
                        "竞品数": t.competitor_count,
                        "时间": t.finished_at.strftime("%m-%d %H:%M") if t.finished_at else "-",
                    } for t in tasks]
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )
    finally:
        session.close()
