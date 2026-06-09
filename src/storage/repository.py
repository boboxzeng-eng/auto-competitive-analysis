"""
数据访问层 — 通用 CRUD 操作
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session

from src.storage.models import (
    Category, CrawlTask, Product, RawSnapshot,
    PriceHistory, ReviewAnalysis, Report, TaskStatus,
)


# -------------------- Category --------------------

def create_category(session: Session, name: str, keywords: list[str]) -> Category:
    cat = Category(name=name, keywords=keywords)
    session.add(cat)
    session.commit()
    return cat


def get_all_categories(session: Session) -> List[Category]:
    return session.query(Category).order_by(Category.created_at.desc()).all()


def get_category_by_name(session: Session, name: str) -> Optional[Category]:
    return session.query(Category).filter(Category.name == name).first()


# -------------------- CrawlTask --------------------

def create_crawl_task(
    session: Session,
    category_id: int,
    platform: str,
    keyword_used: str,
) -> CrawlTask:
    task = CrawlTask(
        category_id=category_id,
        platform=platform,
        keyword_used=keyword_used,
        status=TaskStatus.PENDING.value,
    )
    session.add(task)
    session.commit()
    return task


def update_task_status(
    session: Session, task_id: int, status: TaskStatus,
    product_count: int = 0, error_message: str | None = None,
):
    task = session.query(CrawlTask).filter(CrawlTask.id == task_id).first()
    if task:
        task.status = status.value
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            task.finished_at = datetime.now()
        if product_count:
            task.product_count = product_count
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


# -------------------- Product --------------------

def save_products(
    session: Session, products: list[dict], task_id: int,
) -> List[Product]:
    """批量保存商品"""
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
            crawl_task_id=task_id,
        )
        orm_list.append(product)
    session.add_all(orm_list)
    session.commit()
    return orm_list


def get_products_by_task(
    session: Session, task_id: int,
) -> List[Product]:
    return session.query(Product).filter(Product.crawl_task_id == task_id).all()


def get_products_by_category(
    session: Session, category_id: int, limit: int = 100,
) -> List[Product]:
    return (
        session.query(Product)
        .filter(Product.category_id == category_id)
        .order_by(Product.crawled_at.desc())
        .limit(limit)
        .all()
    )


# -------------------- Price History --------------------

def save_price_history(
    session: Session, product_id: int, price: float,
) -> PriceHistory:
    ph = PriceHistory(product_id=product_id, price=price)
    session.add(ph)
    session.commit()
    return ph


def get_price_history(
    session: Session, product_id: int, days: int = 30,
) -> List[PriceHistory]:
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


# -------------------- Raw Snapshot --------------------

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


def get_snapshots_by_task(
    session: Session, task_id: int,
) -> List[RawSnapshot]:
    return (
        session.query(RawSnapshot)
        .filter(RawSnapshot.crawl_task_id == task_id)
        .all()
    )


# -------------------- Report --------------------

def save_report(
    session: Session,
    category_id: int,
    title: str,
    summary: str = "",
    charts_json: dict | None = None,
) -> Report:
    report = Report(
        category_id=category_id,
        title=title,
        summary=summary,
        charts_json=charts_json,
        data_range_start=datetime.now(),
        data_range_end=datetime.now(),
    )
    session.add(report)
    session.commit()
    return report


def get_reports_by_category(
    session: Session, category_id: int,
) -> List[Report]:
    return (
        session.query(Report)
        .filter(Report.category_id == category_id)
        .order_by(Report.created_at.desc())
        .all()
    )
