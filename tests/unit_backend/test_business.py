"""Модульные тесты бизнес-правил: выбор правила лояльности, расчет выгоды, выгрузки, разбор данных касс."""
import csv
import io
import time
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.models.loyalty import LoyaltyRule
from app.routers.sync import parse_amount, parse_datetime_flexible
from app.services.ai_gateway import CircuitBreaker
from app.services.auth import LoginThrottle
from app.services.exports import build_csv, build_xlsx, safe_cell
from app.services.loyalty import calculate_benefit, select_best_rule


def rule(rid, cluster, rtype, value, min_check="0", active=True):
    return LoyaltyRule(id=rid, cluster_id=cluster, rule_name=f"Правило {rid}", reward_type=rtype,
                       reward_value=Decimal(value), min_check_amount=Decimal(min_check), days_valid=30, is_active=active)


RULES = [rule(1, None, "скидка", "5"), rule(2, 10, "скидка", "15"), rule(3, 10, "кешбэк", "10", "100"),
         rule(4, 20, "скидка", "30"), rule(5, None, "скидка", "50", active=False)]


def test_segment_rule_beats_general():
    assert select_best_rule(RULES, 10, set(), set(), Decimal("50")).id == 2


def test_max_benefit_among_same_priority():
    assert select_best_rule(RULES, 10, set(), set(), Decimal("200")).id == 2


def test_manual_inclusion_has_highest_priority():
    assert select_best_rule(RULES, 10, {4}, set(), Decimal("50")).id == 4


def test_exclusion_and_inactive_rules_are_ignored():
    assert select_best_rule(RULES, 10, set(), {2, 3}, Decimal("200")).id == 1
    assert select_best_rule(RULES, None, set(), {1}, Decimal("200")) is None


def test_min_check_amount():
    assert select_best_rule([RULES[2]], 10, set(), set(), Decimal("99.99")) is None


@pytest.mark.parametrize("r, amount, discount, bonus, final", [
    (rule(1, None, "скидка", "15"), "200.00", "30.00", "0.00", "170.00"),
    (rule(2, None, "скидка", "7.5"), "33.33", "2.50", "0.00", "30.83"),
    (rule(3, None, "кешбэк", "10"), "150.55", "0.00", "15.06", "150.55"),
    (rule(4, None, "баллы", "300"), "80.00", "0.00", "300", "80.00"),
    (None, "80.00", "0.00", "0.00", "80.00"),
])
def test_benefit_calculation(r, amount, discount, bonus, final):
    benefit = calculate_benefit(r, Decimal(amount))
    assert (benefit.discount, benefit.bonus, benefit.final) == (Decimal(discount), Decimal(bonus), Decimal(final))


@pytest.mark.parametrize("value, expected", [
    ('=HYPERLINK("x")', "'=HYPERLINK(\"x\")"), ("+1+1", "'+1+1"), ("-5", "'-5"), ("@SUM(A1)", "'@SUM(A1)"),
    ("+375291234567", "+375291234567"), ("Иванов", "Иванов"), (None, ""),
])
def test_csv_injection_protection(value, expected):
    assert safe_cell(value) == expected


def test_csv_has_bom_and_semicolon():
    data = build_csv(["ФИО", "Сумма"], [["=cmd", 10.5]])
    assert data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert rows == [["ФИО", "Сумма"], ["'=cmd", "10.5"]]


def test_xlsx_export():
    workbook = load_workbook(io.BytesIO(build_xlsx(["Телефон", "Сумма"], [["+375291234567", 12.5]])))
    sheet = workbook.active
    assert sheet["A1"].value == "Телефон" and sheet["A1"].font.bold
    assert sheet["A2"].value == "+375291234567" and sheet["B2"].value == 12.5


@pytest.mark.parametrize("raw", ["2026-01-25 14:30:00", "25.01.2026 14:30", "2026-01-25T14:30:00", "25.01.2026"])
def test_parse_dates(raw):
    parsed = parse_datetime_flexible(raw)
    assert (parsed.year, parsed.month, parsed.day) == (2026, 1, 25) and parsed.tzinfo is not None


def test_parse_date_rejects_garbage():
    with pytest.raises(ValueError):
        parse_datetime_flexible("вчера")


def test_parse_amount():
    assert parse_amount("1 234,50") == Decimal("1234.50")


def test_circuit_breaker_states():
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=0.05)
    breaker.failure()
    assert breaker.state == "closed"
    breaker.failure()
    assert breaker.state == "open" and not breaker.allow()
    time.sleep(0.06)
    assert breaker.state == "half-open" and breaker.allow()
    breaker.failure()
    assert breaker.state == "open"
    time.sleep(0.06)
    breaker.success()
    assert breaker.state == "closed"


def test_login_throttle():
    throttle = LoginThrottle(max_failures=3, lock_seconds=60)
    assert not throttle.register_failure("user")
    assert not throttle.register_failure("USER")
    assert throttle.register_failure("user")
    assert throttle.remaining_lock("user") > 0
    throttle.reset("user")
    assert throttle.remaining_lock("user") == 0
