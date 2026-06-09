"""
数据访问层 — 通用 CRUD 操作
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session

from src.storage.models import (
    Category, CrawlTask, Product, RawSnapshot,
    PriceHistory, ReviewAnalysis, Report,
    CompetitiveProfile, TaskStatus,
)


# ==================== CompetitiveProfile ====================

def create_profile(
    session: Session,
    name: str,
    product_name: str,
    category: str,
    brand: str = "",
    price_min: float = None,
    price_max: float = None,
    specs: dict = None,
    match_weights: dict = None,
    platforms: list[str] = None,
) -> CompetitiveProfile:
    """创建竞品对标画像"""
    profile = CompetitiveProfile(
        name=name,
        product_name=product_name,
        brand=brand,
        category=category,
        price_min=price_min,
        price_max=price_max,
        specs_json=specs,
        match_weights_json=match_weights,
        platforms_json=platforms,
    )
    session.add(profile)
    session.commit()
    return profile


def get_all_profiles(session: Session) -> List[CompetitiveProfile]:
    """获取所有竞品画像"""
    return (
        session.query(CompetitiveProfile)
        .order_by(CompetitiveProfile.created_at.desc())
        .all()
    )


def get_profile_by_id(session: Session, profile_id: int) -> Optional[CompetitiveProfile]:
    return session.query(CompetitiveProfile).filter(CompetitiveProfile.id == profile_id).first()


# ==================== Category ====================

def create_category(session: Session, name: str, keywords: list[str]) -> Category:
    cat = Category(name=name, keywords=keywords)
    session.add(cat)
    session.commit()
    return cat


def get_all_categories(session: Session) -> List[Category]:
    return session.query(Category).order_by(Category.created_at.desc()).all()


def get_category_by_name(session: Session, name: str) -> Optional[Category]:
    return session.query(Category).filter(Category.name == name).first()


# ==================== CrawlTask ====================

def create_crawl_task(
    session: Session,
    platform: str,
    keyword_used: str,
    category_id: int = None,
    profile_id: int = None,
    profile_json: dict = None,
) -> CrawlTask:
    """创建爬取任务 (支持竞品画像)"""
    task = CrawlTask(
        category_id=category_id,
        profile_id=profile_id,
        platform=platform,
        keyword_used=keyword_used,
        profile_json=profile_json,
        status=TaskStatus.PENDING.value,
    )
    session.add(task)
    session.commit()
    return task


def update_task_status(
    session: Session,
    task_id: int,
    status: TaskStatus,
    product_count: int = 0,
    competitor_count: int = 0,
    error_message: str | None = None,
):
    """更新任务状态"""
    task = session.query(CrawlTask).filter(CrawlTask.id == task_id).first()
    if task:
        task.status = status.value
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            task.finished_at = datetime.now()
        if product_count:
            task.product_count = product_count
        if competitor_count:
            task.competitor_count = competitor_count
        if error_message:
            task.error_message = error_message
        session.commit()


def get_tasks_by_category(session: Session, category_id: int) -> List[CrawlTask]:
    return (
        session.query(CrawlTask)
        .filter(CrawlTask.category_id == category_id)
        .order_by(CrawlTask.created_at.desc())
        .all()
    )


def get_tasks_by_profile(session: Session, profile_id: int) -> List[CrawlTask]:
    return (
        session.query(CrawlTask)
        .filter(CrawlTask.profile_id == profile_id)
        .order_by(CrawlTask.created_at.desc())
        .all()
    )


def get_latest_completed_task(
    session: Session, category_id: int, platform: str,
) -> Optional[CrawlTask]:
    return (
        session.query(CrawlTask)
        .filter(
            CrawlTask.category_id == category_id,
            CrawlTask.platform == platform,
            CrawlTask.status == TaskStatus.COMPLETED.value,
        )
        .order_by(CrawlTask.finished_at.desc())
        .first()
    )


# ==================== Product ====================

def save_products(
    session: Session, products: list[dict], task_id: int,
) -> List[Product]:
    """批量保存商品 (含竞品字段)"""
    orm_list = []
    for p in products:
        product = Product(
            platform=p.get("platform"),
            product_id=p.get("product_id"),
            title=p.get("title"),
            price=p.get("price"),
            original_price=p.get("original_price"),
            sales_volume=p.get("sales_volume"),
            shop_name=p.get("shop_name"),
            brand=p.get("brand"),
            category_id=p.get("category_id"),
            url=p.get("url"),
            image_url=p.get("image_url"),
            rating=p.get("rating"),
            comment_count=p.get("comment_count"),
            competitor_score=p.get("competitor_score"),
            match_details=p.get("match_details"),
            is_competitor=p.get("is_competitor", False),
            crawl_task_id=task_id,
        )
        orm_list.append(product)
    session.add_all(orm_list)
    session.commit()
    return orm_list


def get_products_by_task(session: Session, task_id: int) -> List[Product]:
    return session.query(Product).filter(Product.crawl_task_id == task_id).all()


def get_products_by_category(
    session: Session, category_id: int, limit: int = 100,
    competitors_only: bool = False,
) -> List[Product]:
    """获取品类下的商品，可按竞品筛选"""
    q = session.query(Product).filter(Product.category_id == category_id)
    if competitors_only:
        q = q.filter(Product.is_competitor == True)
    return q.order_by(Product.competitor_score.desc().nullslast()).limit(limit).all()


def get_competitors_by_task(
    session: Session, task_id: int, min_score: float = 0,
) -> List[Product]:
    """获取某任务的竞品列表"""
    return (
        session.query(Product)
        .filter(
            Product.crawl_task_id == task_id,
            Product.is_competitor == True,
            Product.competitor_score >= min_score,
        )
        .order_by(Product.competitor_score.desc())
        .all()
    )


# ==================== Price History ====================

def save_price_history(session: Session, product_id: int, price: float) -> PriceHistory:
    ph = PriceHistory(product_id=product_id, price=price)
    session.add(ph)
    session.commit()
    return ph


def get_price_history(session: Session, product_id: int, days: int = 30) -> List[PriceHistory]:
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    return (
        session.query(PriceHistory)
        .filter(
            PriceHistory.product_id == product_id,
            PriceHistory.recorded_at >= cutoff,
        )
        .order_by(PriceHistory.recorded_at.asc())
        .all()
    )


# ==================== Raw Snapshot ====================

def save_raw_snapshot(
    session: Session,
    task_id: int,
    platform: str,
    raw_html: str | None = None,
    raw_json: dict | None = None,
    product_id: int | None = None,
) -> RawSnapshot:
    snapshot = RawSnapshot(
        crawl_task_id=task_id,
        product_id=product_id,
        platform=platform,
        raw_html=raw_html,
        raw_json=raw_json,
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def get_snapshots_by_task(session: Session, task_id: int) -> List[RawSnapshot]:
    return (
        session.query(RawSnapshot)
        .filter(RawSnapshot.crawl_task_id == task_id)
        .all()
    )


# ==================== Report ====================

def save_report(
    session: Session,
    category_id: int,
    title: str,
    summary: str = "",
    charts_json: dict | None = None,
    profile_id: int = None,
    compliance_note: str = "",
) -> Report:
    report = Report(
        category_id=category_id,
        profile_id=profile_id,
        title=title,
        summary=summary,
        charts_json=charts_json,
        compliance_note=compliance_note,
        data_range_start=datetime.now(),
        data_range_end=datetime.now(),
    )
    session.add(report)
    session.commit()
    return report


def get_reports_by_category(session: Session, category_id: int) -> List[Report]:
    return (
        session.query(Report)
        .filter(Report.category_id == category_id)
        .order_by(Report.created_at.desc())
        .all()
    )
