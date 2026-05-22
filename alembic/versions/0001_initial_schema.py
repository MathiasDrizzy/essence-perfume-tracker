"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "perfumes",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("brand", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("concentration", sa.Text),
        sa.Column("volume_ml", sa.Integer, nullable=False),
        sa.Column("gender", sa.Text),
        sa.Column("canonical_slug", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_perfumes_brand_name", "perfumes", ["brand", "name"])

    op.create_table(
        "listings",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("perfume_id", sa.BigInteger, sa.ForeignKey("perfumes.id"), nullable=False),
        sa.Column("retailer", sa.Text, nullable=False),
        sa.Column("retailer_sku", sa.Text),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title_raw", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, server_default=sa.true()),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("retailer", "url", name="uq_listings_retailer_url"),
    )
    op.create_index("ix_listings_perfume_id", "listings", ["perfume_id"])

    op.create_table(
        "price_history",
        sa.Column("listing_id", sa.BigInteger, sa.ForeignKey("listings.id"), primary_key=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("price_clp", sa.Integer, nullable=False),
        sa.Column("list_price_clp", sa.Integer),
        sa.Column("in_stock", sa.Boolean),
    )
    op.create_index(
        "ix_price_history_scraped_at_brin",
        "price_history",
        ["scraped_at"],
        postgresql_using="brin",
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("perfume_id", sa.BigInteger, sa.ForeignKey("perfumes.id"), nullable=False),
        sa.Column("target_price_clp", sa.Integer, nullable=False),
        sa.Column("telegram_chat_id", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, server_default=sa.true()),
        sa.Column("triggered_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("retailer", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("products_scraped", sa.Integer),
        sa.Column("status", sa.String(16)),
        sa.Column("error", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("alerts")
    op.drop_index("ix_price_history_scraped_at_brin", table_name="price_history")
    op.drop_table("price_history")
    op.drop_index("ix_listings_perfume_id", table_name="listings")
    op.drop_table("listings")
    op.drop_index("ix_perfumes_brand_name", table_name="perfumes")
    op.drop_table("perfumes")
