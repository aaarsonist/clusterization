from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

REWARD_DISCOUNT = "скидка"
REWARD_POINTS = "баллы"
REWARD_CASHBACK = "кешбэк"


class LoyaltyRule(Base):
    __tablename__ = "loyalty_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cluster_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("clusters.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    rule_name: Mapped[str] = mapped_column(String(255))
    reward_type: Mapped[str] = mapped_column(String(16))
    reward_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    min_check_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    days_valid: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class LoyaltyRuleCustomClient(Base):
    __tablename__ = "loyalty_rule_custom_clients"

    rule_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("loyalty_rules.id", ondelete="CASCADE"), primary_key=True)
    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())
