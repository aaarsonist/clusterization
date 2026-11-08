"""Формирование выгрузок CSV (UTF-8 с BOM для Microsoft Excel) и XLSX с защитой от формульных инъекций."""
import csv
import io
import re
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
PHONE_RE = re.compile(r"^\+\d{11,15}$")
CSV_MEDIA = "text/csv; charset=utf-8"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def safe_cell(value) -> str:
    """Нейтрализация CSV/формульной инъекции: текст, начинающийся со спецсимвола, экранируется апострофом.

    Номера телефонов в формате E.164 (только «+» и цифры) формулой быть не могут и не изменяются.
    """
    if value is None:
        return ""
    text = str(value)
    if PHONE_RE.match(text):
        return text
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def build_csv(headers: Sequence[str], rows: Iterable[Sequence]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect="excel", delimiter=";")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return buffer.getvalue().encode("utf-8-sig")


def build_xlsx(headers: Sequence[str], rows: Iterable[Sequence], sheet: str = "Выгрузка") -> bytes:
    workbook = Workbook()
    ws = workbook.active
    ws.title = sheet[:31]
    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([safe_cell(v) if isinstance(v, str) else v for v in row])
    for column in ws.columns:
        width = max(len(str(c.value or "")) for c in column)
        ws.column_dimensions[column[0].column_letter].width = min(60, max(10, width + 2))
    ws.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def slug(text: str) -> str:
    return re.sub(r"[^\wа-яё0-9]+", "_", (text or "").lower(), flags=re.UNICODE).strip("_") or "all"


def file_response(headers: Sequence[str], rows: list[Sequence], base_name: str, fmt: str) -> Response:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if fmt == "xlsx":
        content, media, ext = build_xlsx(headers, rows), XLSX_MEDIA, "xlsx"
    else:
        content, media, ext = build_csv(headers, rows), CSV_MEDIA, "csv"
    filename = quote(f"{base_name}_{stamp}.{ext}")
    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{filename}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
