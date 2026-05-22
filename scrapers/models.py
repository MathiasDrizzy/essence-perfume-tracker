from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Perfume(Base):
    __tablename__ = "perfumes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    brand: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    concentration: Mapped[str | None] = mapped_column(Text)
    volume_ml: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(Text)
    canonical_slug: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    listings: Mapped[list["Listing"]] = relationship(back_populates="perfume")

    __table_args__ = (Index("ix_perfumes_brand_name", "brand", "name"),)


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    perfume_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("perfumes.id"))
    retailer: Mapped[str] = mapped_column(Text)
    retailer_sku: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    title_raw: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    perfume: Mapped[Perfume] = relationship(back_populates="listings")
    prices: Mapped[list["PriceHistory"]] = relationship(back_populates="listing")

    __table_args__ = (
        UniqueConstraint("retailer", "url", name="uq_listings_retailer_url"),
        Index("ix_listings_perfume_id", "perfume_id"),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    listing_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("listings.id"), primary_key=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    price_clp: Mapped[int] = mapped_column(Integer)
    list_price_clp: Mapped[int | None] = mapped_column(Integer)
    in_stock: Mapped[bool | None] = mapped_column(Boolean)

    listing: Mapped[Listing] = relationship(back_populates="prices")

    __table_args__ = (
        Index("ix_price_history_scraped_at_brin", "scraped_at", postgresql_using="brin"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    perfume_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("perfumes.id"))
    target_price_clp: Mapped[int] = mapped_column(Integer)
    telegram_chat_id: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    retailer: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    products_scraped: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
