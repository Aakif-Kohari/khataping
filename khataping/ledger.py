"""Deterministic ledger maths.

Everything that involves money lives here, in plain Python. The language model
never sees a raw ledger and never does arithmetic - it only phrases a message
around numbers computed by this module.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

REQUIRED_COLUMNS = {"customer", "date", "type", "amount"}
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")
CREDIT_WORDS = {"credit", "udhaar", "udhar"}
PAYMENT_WORDS = {"payment", "paid", "jama"}

# Days since the oldest still-unpaid credit -> bucket name.
BUCKETS = (
    (14, "fresh"),
    (30, "due"),
    (60, "overdue"),
)
LONGEST_BUCKET = "long_overdue"


class LedgerError(ValueError):
    """Raised when the ledger CSV cannot be understood."""


@dataclass(frozen=True)
class Entry:
    customer: str
    phone: str
    day: date
    kind: str  # "credit" or "payment"
    amount: float


@dataclass(frozen=True)
class CustomerDue:
    name: str
    phone: str
    outstanding: float
    oldest_due: Optional[date]
    days_overdue: int
    last_payment: Optional[date]
    bucket: str  # clear | fresh | due | overdue | long_overdue


def _parse_date(raw: str, line: int) -> date:
    raw = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise LedgerError(
        f"Line {line}: cannot read date {raw!r}. Use YYYY-MM-DD or DD-MM-YYYY."
    )


def _parse_amount(raw: str, line: int) -> float:
    cleaned = (raw or "").replace("\u20b9", "").replace(",", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        raise LedgerError(f"Line {line}: cannot read amount {raw!r}.") from None
    if value <= 0:
        raise LedgerError(f"Line {line}: amount must be greater than zero.")
    return value


def _parse_kind(raw: str, line: int) -> str:
    word = (raw or "").strip().lower()
    if word in CREDIT_WORDS:
        return "credit"
    if word in PAYMENT_WORDS:
        return "payment"
    raise LedgerError(
        f"Line {line}: type must be one of credit/udhaar (given on credit) "
        f"or payment/paid/jama (money received), got {raw!r}."
    )


def parse_ledger(text: str) -> list[Entry]:
    """Parse ledger CSV text into entries.

    Columns: customer, date, type, amount (required); phone, note (optional).
    """
    if not text or not text.strip():
        raise LedgerError("The ledger is empty.")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise LedgerError(
            "Missing column(s): " + ", ".join(sorted(missing))
            + ". Expected: customer, date, type, amount (optional: phone, note)."
        )
    entries: list[Entry] = []
    for idx, row in enumerate(reader, start=2):  # header is line 1
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not any(row.values()):
            continue
        name = row.get("customer", "")
        if not name:
            raise LedgerError(f"Line {idx}: customer name is empty.")
        entries.append(
            Entry(
                customer=name,
                phone=row.get("phone", ""),
                day=_parse_date(row.get("date", ""), idx),
                kind=_parse_kind(row.get("type", ""), idx),
                amount=_parse_amount(row.get("amount", ""), idx),
            )
        )
    if not entries:
        raise LedgerError("No ledger rows found.")
    return entries


def bucket_for(days: int) -> str:
    for limit, name in BUCKETS:
        if days <= limit:
            return name
    return LONGEST_BUCKET


def compute_dues(entries: Iterable[Entry], today: date) -> list[CustomerDue]:
    """Per-customer outstanding balance using first-in-first-out settlement.

    Payments are applied to the oldest credit first, so "days overdue" is the
    age of the oldest credit that is still (even partly) unpaid.
    """
    by_customer: dict[str, list[Entry]] = {}
    display: dict[str, str] = {}
    for e in entries:
        key = e.customer.strip().lower()
        by_customer.setdefault(key, []).append(e)
        display.setdefault(key, e.customer.strip())

    result: list[CustomerDue] = []
    for key, rows in by_customer.items():
        credits = sorted((e.day, e.amount) for e in rows if e.kind == "credit")
        payments = [e for e in rows if e.kind == "payment"]
        paid = sum(p.amount for p in payments)

        remaining: list[tuple[date, float]] = []
        for day, amount in credits:
            if paid >= amount - 1e-9:
                paid -= amount
                continue
            remaining.append((day, amount - paid))
            paid = 0.0

        outstanding = round(sum(a for _, a in remaining), 2)
        phones = [e.phone for e in sorted(rows, key=lambda r: r.day) if e.phone]
        last_payment = max((p.day for p in payments), default=None)

        if outstanding <= 0.005:
            result.append(
                CustomerDue(display[key], phones[-1] if phones else "", 0.0, None, 0,
                            last_payment, "clear")
            )
            continue

        oldest = remaining[0][0]
        days = max((today - oldest).days, 0)
        result.append(
            CustomerDue(display[key], phones[-1] if phones else "", outstanding,
                        oldest, days, last_payment, bucket_for(days))
        )
    return result


def customers_with_dues(dues: Iterable[CustomerDue]) -> list[CustomerDue]:
    """Only customers who owe money, most overdue (then largest) first."""
    owing = [d for d in dues if d.outstanding > 0.005]
    return sorted(owing, key=lambda d: (-d.days_overdue, -d.outstanding, d.name.lower()))
