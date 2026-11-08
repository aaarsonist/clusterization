"""Бизнес-правила программы лояльности: выбор применимого правила и расчет выгоды по чеку."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models.loyalty import REWARD_CASHBACK, REWARD_DISCOUNT, LoyaltyRule

CENT = Decimal("0.01")


def ru(value: Decimal, money: bool = False) -> str:
    """Число в русской записи: десятичная запятая, без незначащих нулей (для сумм — два знака)."""
    if money:
        return f"{value.quantize(CENT, ROUND_HALF_UP):.2f}".replace(".", ",")
    text = f"{value.normalize():f}"
    return text.replace(".", ",")


@dataclass
class Benefit:
    discount: Decimal
    bonus: Decimal
    final: Decimal
    description: str


def rule_weight(rule: LoyaltyRule, cluster_id: int | None, included: set[int]) -> int:
    """Приоритет правила: 2 — ручное прикрепление, 1 — правило сегмента клиента, 0 — общее правило."""
    if rule.id in included:
        return 2
    if cluster_id is not None and rule.cluster_id == cluster_id:
        return 1
    return 0


def applicable_rules(
    rules: list[LoyaltyRule],
    cluster_id: int | None,
    included: set[int],
    excluded: set[int],
    check_amount: Decimal | None = None,
) -> list[LoyaltyRule]:
    """Отбор активных правил, распространяющихся на клиента, с учетом ручных включений и исключений."""
    result = []
    for rule in rules:
        if not rule.is_active or rule.id in excluded:
            continue
        if check_amount is not None and rule.min_check_amount > check_amount:
            continue
        if rule.id in included or rule.cluster_id is None or (cluster_id is not None and rule.cluster_id == cluster_id):
            result.append(rule)
    return result


def select_best_rule(
    rules: list[LoyaltyRule],
    cluster_id: int | None,
    included: set[int],
    excluded: set[int],
    check_amount: Decimal | None = None,
) -> LoyaltyRule | None:
    """Выбор правила с наибольшим приоритетом, а при равенстве — с наибольшей выгодой для клиента."""
    candidates = applicable_rules(rules, cluster_id, included, excluded, check_amount)
    if not candidates:
        return None

    def benefit_value(rule: LoyaltyRule) -> Decimal:
        if check_amount is not None and rule.reward_type in (REWARD_DISCOUNT, REWARD_CASHBACK):
            return check_amount * rule.reward_value / 100
        return rule.reward_value

    return max(candidates, key=lambda r: (rule_weight(r, cluster_id, included), benefit_value(r), -r.id))


def calculate_benefit(rule: LoyaltyRule | None, amount: Decimal) -> Benefit:
    amount = amount.quantize(CENT, ROUND_HALF_UP)
    if rule is None:
        return Benefit(Decimal("0.00"), Decimal("0.00"), amount, "Для данного чека нет подходящих активных предложений.")
    value = rule.reward_value
    if rule.reward_type == REWARD_DISCOUNT:
        discount = (amount * value / 100).quantize(CENT, ROUND_HALF_UP)
        return Benefit(discount, Decimal("0.00"), amount - discount,
                       f"Персональная скидка {ru(value)} %: экономия {ru(discount, True)} BYN.")
    if rule.reward_type == REWARD_CASHBACK:
        bonus = (amount * value / 100).quantize(CENT, ROUND_HALF_UP)
        return Benefit(Decimal("0.00"), bonus, amount, f"Кешбэк {ru(value)} %: на бонусный счет начислено {ru(bonus, True)} BYN.")
    return Benefit(Decimal("0.00"), value, amount, f"Начислено {ru(value)} бонусных баллов.")


def describe_reward(rule: LoyaltyRule | None) -> str:
    if rule is None:
        return "—"
    value = ru(rule.reward_value)
    return {"скидка": f"Скидка {value} %", "кешбэк": f"Кешбэк {value} %"}.get(rule.reward_type, f"{value} баллов")
