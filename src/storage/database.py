"""
数据库连接管理
"""

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from src.config import DATABASE_URL

# SQLAlchemy Base
Base = declarative_base()

# 引擎 (单例)
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    """获取数据库引擎 (懒加载)"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            echo=False,            # 生产环境关闭 SQL 日志
            connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
        )
    return _engine


def get_session() -> Session:
    """获取数据库会话"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db():
    """初始化数据库 — 创建所有表"""
    from src.storage import models  # noqa: F401 — 导入以注册模型
    Base.metadata.create_all(bind=get_engine())


def drop_db():
    """删除所有表 (仅开发用)"""
    Base.metadata.drop_all(bind=get_engine())
