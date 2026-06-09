"""
SQLAlchemy ORM 模型定义

核心表:
- Category: 品类
- CrawlTask: 爬取任务
- Product: 商品 (核心)
- RawSnapshot: 原始快照 (溯源)
- PriceHistory: 价格历史
- ReviewAnalysis: 评价分析
- Report: 分析报告
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime,
    ForeignKey, JSON, Boolean, Enum as SAEnum,
)
from sqlalchemy.orm import relationship
import enum

from src.storage.database import Base


# -------------------- 枚举 --------------------

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Platform(str, enum.Enum):
    JD = "jd"
    TAOBAO = "taobao"
    PDD = "pdd"
    DOUYIN = "douyin"


# -------------------- 模型 --------------------

class Category(Base):
    """品类表"""
    __tablename__ = "category"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="品类名称")
    keywords = Column(JSON, nullable=False, comment="搜索关键词列表")
    parent_id = Column(Integer, ForeignKey("category.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    # 关系
    products = relationship("Product", back_populates="category")
    crawl_tasks = relationship("CrawlTask", back_populates="category")


class CrawlTask(Base):
    """爬取任务表"""
    __tablename__ = "crawl_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False)
    platform = Column(String(20), nullable=False, comment="平台")
    status = Column(String(20), default=TaskStatus.PENDING.value)
    keyword_used = Column(String(200), comment="实际使用的搜索关键词")
    error_message = Column(Text, nullable=True)
    product_count = Column(Integer, default=0, comment="采集到的商品数")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    # 关系
    category = relationship("Category", back_populates="crawl_tasks")
    products = relationship("Product", back_populates="crawl_task")
    raw_snapshots = relationship("RawSnapshot", back_populates="crawl_task")


class Product(Base):
    """商品表 (核心)"""
    __tablename__ = "product"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False, comment="来源平台")
    product_id = Column(String(100), nullable=False, comment="平台商品ID")
    title = Column(String(500), nullable=False, comment="商品标题")
    price = Column(Float, nullable=True, comment="当前售价")
    original_price = Column(Float, nullable=True, comment="原价")
    sales_volume = Column(Integer, nullable=True, comment="销量")
    shop_name = Column(String(200), nullable=True, comment="店铺名称")
    brand = Column(String(100), nullable=True, comment="品牌")
    category_id = Column(Integer, ForeignKey("category.id"), nullable=True)
    url = Column(String(1000), nullable=True, comment="商品链接")
    image_url = Column(String(1000), nullable=True, comment="主图链接")
    rating = Column(Float, nullable=True, comment="评分")
    comment_count = Column(Integer, nullable=True, comment="评价数")
    crawl_task_id = Column(Integer, ForeignKey("crawl_task.id"), nullable=False)
    crawled_at = Column(DateTime, default=datetime.now, comment="采集时间")

    # 关系
    category = relationship("Category", back_populates="products")
    crawl_task = relationship("CrawlTask", back_populates="products")
    price_histories = relationship("PriceHistory", back_populates="product")
    review_analyses = relationship("ReviewAnalysis", back_populates="product")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "product_id": self.product_id,
            "title": self.title,
            "price": self.price,
            "original_price": self.original_price,
            "sales_volume": self.sales_volume,
            "shop_name": self.shop_name,
            "brand": self.brand,
            "url": self.url,
            "image_url": self.image_url,
            "rating": self.rating,
            "comment_count": self.comment_count,
            "crawled_at": self.crawled_at.isoformat() if self.crawled_at else None,
        }


class RawSnapshot(Base):
    """原始快照表 (溯源核心)"""
    __tablename__ = "raw_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    crawl_task_id = Column(Integer, ForeignKey("crawl_task.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=True)
    platform = Column(String(20), nullable=False)
    raw_html = Column(Text, nullable=True, comment="原始 HTML")
    raw_json = Column(JSON, nullable=True, comment="原始 JSON/API 响应")
    crawled_at = Column(DateTime, default=datetime.now)

    # 关系
    crawl_task = relationship("CrawlTask", back_populates="raw_snapshots")


class PriceHistory(Base):
    """价格历史表"""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.now)

    # 关系
    product = relationship("Product", back_populates="price_histories")


class ReviewAnalysis(Base):
    """评价分析表"""
    __tablename__ = "review_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    rating_avg = Column(Float, nullable=True, comment="平均评分")
    review_count = Column(Integer, nullable=True, comment="评价数")
    positive_rate = Column(Float, nullable=True, comment="好评率")
    keywords_json = Column(JSON, nullable=True, comment="高频词云")
    sentiment_score = Column(Float, nullable=True, comment="情感得分")
    analyzed_at = Column(DateTime, default=datetime.now)

    # 关系
    product = relationship("Product", back_populates="review_analyses")


class Report(Base):
    """分析报告表"""
    __tablename__ = "report"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=True, comment="报告摘要")
    charts_json = Column(JSON, nullable=True, comment="图表数据 JSON")
    data_range_start = Column(DateTime, nullable=True)
    data_range_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
