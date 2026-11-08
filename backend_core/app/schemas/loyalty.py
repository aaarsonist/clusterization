from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RewardType = Literal["скидка", "баллы", "кешбэк"]


class RuleBase(BaseModel):
    cluster_id: int | None = Field(None, description="Целевой сегмент или null для общего правила")
    rule_name: str = Field(..., min_length=3, max_length=255)
    reward_type: RewardType
    reward_value: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    min_check_amount: Decimal = Field(Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    days_valid: int = Field(30, gt=0, le=3650)
    is_active: bool = True

    @model_validator(mode="after")
    def check_percent(self):
        if self.reward_type != "баллы" and self.reward_value > 100:
            raise ValueError("Размер скидки или кешбэка не может превышать 100 %")
        return self


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    cluster_id: int | None = None
    rule_name: str | None = Field(None, min_length=3, max_length=255)
    reward_type: RewardType | None = None
    reward_value: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    min_check_amount: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    days_valid: int | None = Field(None, gt=0, le=3650)
    is_active: bool | None = None


class RuleOut(BaseModel):
    id: int
    cluster_id: int | None
    cluster_label: str
    segment_code: str | None = None
    rule_name: str
    reward_type: str
    reward_value: Decimal
    min_check_amount: Decimal
    days_valid: int
    is_active: bool
    audience_count: int = 0
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class AudienceClient(BaseModel):
    client_id: int
    external_code: str
    full_name: str
    phone: str
    cluster_label: str
    total_spent: Decimal
    is_custom_included: bool = False


class AudienceResponse(BaseModel):
    rule_id: int
    rule_name: str
    cluster_label: str
    total_count: int
    excluded_count: int
    clients: list[AudienceClient]


class AttachClientRequest(BaseModel):
    client_id: int


class DiscountRequest(BaseModel):
    client_id: int | None = None
    phone: str | None = Field(None, max_length=32)
    check_amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)


class DiscountResponse(BaseModel):
    client_id: int
    client_name: str
    external_code: str
    cluster_label: str
    applied_rule_id: int | None
    applied_rule_name: str | None
    reward_type: str | None
    reward_value: Decimal | None
    original_amount: Decimal
    discount_amount: Decimal
    bonus_amount: Decimal
    final_amount: Decimal
    benefit_description: str
