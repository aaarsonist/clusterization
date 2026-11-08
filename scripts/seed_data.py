#!/usr/bin/env python3
"""Генерация синтетических данных: учетные записи, клиенты (с шифрованием контактов) и чеки.

Клиенты распределяются по четырем скрытым поведенческим группам (эталонная разметка
используется при валидации интеллектуального компонента):
  VIP (15 %)      — частые крупные покупки, последняя покупка 1–18 дней назад;
  NEWBIE (25 %)   — 1–2 покупки за последние 5–75 дней;
  CHURN (25 %)    — 4–8 покупок в прошлом, последняя 65–300 дней назад;
  BARGAIN (35 %)  — частые небольшие покупки с высокой долей скидок.
Запуск в контейнере сервера: docker compose exec backend_core python /app/scripts/seed_data.py
"""
import argparse
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.core.security import (  # noqa: E402
    email_hash,
    encrypt_pii,
    hash_password,
    normalize_phone,
    phone_hash,
    phone_tail_hash,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed_data")

SHARES = (("VIP", 0.15), ("NEWBIE", 0.25), ("CHURN", 0.25), ("BARGAIN", 0.35))
LAST_M = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Федоров",
          "Морозов", "Волков", "Алексеев", "Лебедев", "Семенов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев"]
FIRST_M = ["Александр", "Михаил", "Максим", "Артем", "Даниил", "Иван", "Дмитрий", "Кирилл", "Никита", "Егор", "Андрей",
           "Илья", "Алексей", "Роман", "Сергей", "Денис", "Павел", "Глеб", "Виктор", "Антон"]
PATR_M = ["Александрович", "Михайлович", "Иванович", "Дмитриевич", "Андреевич", "Алексеевич", "Сергеевич", "Павлович",
          "Викторович", "Романович"]
FIRST_F = ["София", "Анна", "Мария", "Алиса", "Виктория", "Полина", "Екатерина", "Ксения", "Анастасия", "Дарья",
           "Вероника", "Александра", "Валерия", "Алина", "Елизавета", "Ольга", "Елена", "Юлия", "Татьяна", "Ирина"]
PATR_F = ["Александровна", "Михайловна", "Ивановна", "Дмитриевна", "Андреевна", "Алексеевна", "Сергеевна", "Павловна",
          "Викторовна", "Романовна"]
DOMAINS = ["mail.ru", "yandex.by", "gmail.com", "tut.by", "inbox.ru"]
OPERATORS = ["29", "33", "44", "25"]
PROFILES = {
    #           чеков      давность    интервал   сумма чека, BYN  доля скидки
    "VIP": ((18, 28), (1, 18), (10, 20), (150, 480), (0.05, 0.10)),
    "NEWBIE": ((1, 2), (5, 75), (10, 30), (40, 140), (0.0, 0.05)),
    "CHURN": ((4, 8), (65, 300), (15, 35), (60, 200), (0.05, 0.12)),
    "BARGAIN": ((10, 18), (3, 40), (12, 26), (20, 75), (0.15, 0.30)),
}


def segment_of_index(i: int, total: int) -> str:
    """Эталонная группа клиента по его порядковому номеру (1..total)."""
    bound = 0.0
    for name, share in SHARES:
        bound += share * total
        if i <= round(bound):
            return name
    return SHARES[-1][0]


def full_name(i: int) -> str:
    if i % 2 == 0:
        return f"{random.choice(LAST_M)} {random.choice(FIRST_M)} {random.choice(PATR_M)}"
    return f"{random.choice(LAST_M)}а {random.choice(FIRST_F)} {random.choice(PATR_F)}"


def connect(retries: int = 15):
    for attempt in range(1, retries + 1):
        try:
            return psycopg2.connect(
                host=os.getenv("POSTGRES_SERVER", "postgres"), port=int(os.getenv("POSTGRES_PORT", "5432")),
                user=os.getenv("POSTGRES_USER", "postgres"), password=os.environ["POSTGRES_PASSWORD"],
                dbname=os.getenv("POSTGRES_DB", "loyalty_db"),
                sslmode="verify-full" if os.getenv("POSTGRES_SSL", "true").lower() == "true" else "disable",
                sslrootcert=os.getenv("TLS_CA_FILE", "/certs/ca.crt"),
            )
        except psycopg2.OperationalError as exc:
            log.warning("Попытка %s/%s: СУБД недоступна (%s)", attempt, retries, exc)
            time.sleep(2)
    raise RuntimeError("Не удалось подключиться к PostgreSQL")


def generate(total: int, now: datetime):
    clients, transactions = [], []
    for i in range(1, total + 1):
        segment = segment_of_index(i, total)
        e164 = normalize_phone(f"+375{OPERATORS[i % 4]}{1000000 + i:07d}")
        email = f"client{i}@{random.choice(DOMAINS)}"
        created = now - timedelta(days=random.randint(300, 400), hours=random.randint(0, 23))
        clients.append((f"CL-{10000 + i}", full_name(i), encrypt_pii(e164), phone_hash(e164), phone_tail_hash(e164),
                        encrypt_pii(email), email_hash(email), created))

        (cnt_lo, cnt_hi), (rec_lo, rec_hi), (int_lo, int_hi), (amt_lo, amt_hi), (d_lo, d_hi) = PROFILES[segment]
        moment = now - timedelta(days=random.randint(rec_lo, rec_hi), hours=random.randint(1, 12))
        for _ in range(random.randint(cnt_lo, cnt_hi)):
            amount = round(random.uniform(amt_lo, amt_hi), 2)
            status = "отменен" if random.random() < 0.03 else "проведен"
            transactions.append((i, moment, amount, round(amount * random.uniform(d_lo, d_hi), 2), status))
            moment -= timedelta(days=random.randint(int_lo, int_hi), hours=random.randint(0, 10))
    return clients, transactions


def seed(total: int, if_empty: bool = False) -> None:
    random.seed(42)
    now = datetime.now(timezone.utc)
    conn = connect()
    try:
        if if_empty:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                if cur.fetchone()[0] > 0:
                    log.info("База данных уже заполнена, генерация пропущена.")
                    return
        with conn, conn.cursor() as cur:
            log.info("Очистка таблиц...")
            cur.execute("""TRUNCATE loyalty_rule_custom_clients, loyalty_rules, client_cluster_history, segmentation_snapshots,
                           client_cluster_mapping, clusters, client_features, segmentation_runs, transactions, clients,
                           audit_log, users RESTART IDENTITY CASCADE""")
            cur.execute("INSERT INTO backup_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
            execute_values(cur, "INSERT INTO users (username, password_hash, role, created_at) VALUES %s", [
                ("admin", hash_password("Admin#2026"), "администратор", now - timedelta(days=120)),
                ("marketer", hash_password("Marketer#2026"), "маркетолог", now - timedelta(days=90)),
            ])
            clients, transactions = generate(total, now)
            execute_values(cur, """INSERT INTO clients (external_code, full_name, phone_enc, phone_hash, phone_tail_hash,
                                   email_enc, email_hash, created_at) VALUES %s""", clients, page_size=2000)
            execute_values(cur, """INSERT INTO transactions (client_id, transaction_date, total_amount, discount_amount, status)
                                   VALUES %s""", transactions, page_size=5000)
            cur.execute("INSERT INTO audit_log (username, action, details) VALUES ('система', 'Генерация демонстрационных данных', %s)",
                        (f'{{"clients": {total}, "transactions": {len(transactions)}}}',))
            cur.execute("""SELECT COUNT(*), COALESCE(SUM(total_amount), 0), COALESCE(AVG(total_amount), 0)
                           FROM transactions WHERE status = 'проведен'""")
            count, revenue, avg = cur.fetchone()
        log.info("Пользователи: admin / Admin#2026 (администратор), marketer / Marketer#2026 (маркетолог)")
        log.info("Клиентов: %s; чеков: %s (проведенных %s); оборот %.2f BYN; средний чек %.2f BYN",
                 total, len(transactions), count, revenue, avg)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Генерация демонстрационных данных")
    parser.add_argument("--clients", type=int, default=1500, help="Количество клиентов (по умолчанию 1500)")
    parser.add_argument("--if-empty", action="store_true", help="Заполнять только пустую базу данных")
    args = parser.parse_args()
    seed(args.clients, args.if_empty)
