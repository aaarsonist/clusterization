from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ClientListItem(BaseModel):
    id: int
    external_code: str
    full_name: str
    phone: str
    last_purchase_date: datetime | None = None
    frequency: int = 0
    total_spent: Decimal = Decimal("0.00")
    cluster_id: int | None = None
    cluster_label: str | None = None
    segment_code: str | None = None


class ClientListResponse(BaseModel):
    items: list[ClientListItem]
    total: int
    page: int
    limit: int
    pages: int


class ClientTransaction(BaseModel):
    id: int
    transaction_date: datetime
    total_amount: Decimal
    discount_amount: Decimal
    status: str


class ClientRuleItem(BaseModel):
    id: int
    rule_name: str
    reward_type: str
    reward_value: Decimal
    min_check_amount: Decimal
    days_valid: int
    source: str


class ClientProfile(BaseModel):
    id: int
    external_code: str
    full_name: str
    phone: str
    email: str
    created_at: datetime
    recency_days: float | None
    frequency: int
    monetary: Decimal
    avg_check: Decimal
    cancelled_count: int
    cluster_id: int | None
    cluster_label: str | None
    segment_code: str | None
    transactions: list[ClientTransaction]
    rules: list[ClientRuleItem]
