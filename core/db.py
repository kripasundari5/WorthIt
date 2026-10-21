"""Database models and session handling."""
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from core.config import DB_URL


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # ASIN/SKU
    title: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    itm_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_ingested: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_products_price", "price"),)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("products.id", ondelete="CASCADE"))
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    helpful_votes: Mapped[int] = mapped_column(Integer, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_reviews_product", "product_id"),
        Index("ix_reviews_processed", "processed"),
    )


class AspectMention(Base):
    """One (aspect, sentiment, evidence) triple from one review."""
    __tablename__ = "aspect_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"))
    product_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("products.id", ondelete="CASCADE"))
    aspect: Mapped[str] = mapped_column(String(64))
    sentiment: Mapped[float] = mapped_column(Float)     # -1.0 .. 1.0
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_mentions_product_aspect", "product_id", "aspect"),)


class AspectScore(Base):
    """Aggregated product x aspect matrix. This is what the ranker reads."""
    __tablename__ = "aspect_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("products.id", ondelete="CASCADE"))
    aspect: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)         # 0.0 .. 1.0
    confidence: Mapped[float] = mapped_column(Float)    # 0.0 .. 1.0
    mentions: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("product_id", "aspect", name="uq_product_aspect"),
    )


# Lazy engine: importing this module must not require a live DB driver.
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal()


def init_db() -> None:
    Base.metadata.create_all(get_engine())
    