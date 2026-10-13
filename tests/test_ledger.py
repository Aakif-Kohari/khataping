from datetime import date

import pytest

from khataping.ledger import (
    LedgerError,
    bucket_for,
    compute_dues,
    customers_with_dues,
    parse_ledger,
)

TODAY = date(2026, 10, 13)


def dues_for(csv_text):
    return {d.name: d for d in compute_dues(parse_ledger(csv_text), TODAY)}


def test_fifo_payment_clears_oldest_credit_first():
    csv_text = (
        "customer,date,type,amount\n"
        "A,2026-07-01,credit,1000\n"
        "A,2026-08-01,credit,500\n"
        "A,2026-08-10,payment,1200\n"
    )
    a = dues_for(csv_text)["A"]
    assert a.outstanding == 300
    # The first credit is fully cleared, so the oldest unpaid one is 2026-08-01.
    assert a.oldest_due == date(2026, 8, 1)
    assert a.days_overdue == 73
    assert a.bucket == "long_overdue"


def test_fully_paid_customer_is_clear_and_not_listed():
    csv_text = (
        "customer,date,type,amount\n"
        "B,2026-10-01,credit,400\n"
        "B,2026-10-05,payment,400\n"
    )
    b = dues_for(csv_text)["B"]
    assert b.bucket == "clear" and b.outstanding == 0
    assert customers_with_dues([b]) == []


def test_overpayment_never_creates_negative_dues():
    csv_text = "customer,date,type,amount\nC,2026-10-01,credit,100\nC,2026-10-02,payment,250\n"
    assert dues_for(csv_text)["C"].outstanding == 0


def test_customer_names_group_case_insensitively():
    csv_text = (
        "customer,date,type,amount\n"
        "Ramesh Patil,2026-10-01,credit,100\n"
        " ramesh patil ,2026-10-02,credit,50\n"
    )
    result = compute_dues(parse_ledger(csv_text), TODAY)
    assert len(result) == 1 and result[0].outstanding == 150


def test_bucket_boundaries():
    assert bucket_for(0) == "fresh"
    assert bucket_for(14) == "fresh"
    assert bucket_for(15) == "due"
    assert bucket_for(30) == "due"
    assert bucket_for(31) == "overdue"
    assert bucket_for(60) == "overdue"
    assert bucket_for(61) == "long_overdue"


def test_sorting_most_overdue_first():
    csv_text = (
        "customer,date,type,amount\n"
        "New,2026-10-10,credit,9000\n"
        "Old,2026-06-01,credit,100\n"
    )
    ordered = customers_with_dues(compute_dues(parse_ledger(csv_text), TODAY))
    assert [d.name for d in ordered] == ["Old", "New"]


def test_accepts_udhaar_jama_rupee_sign_and_indian_dates():
    csv_text = (
        "customer,date,type,amount\n"
        "D,01-10-2026,udhaar,₹1,200\n"
        "D,05/10/2026,jama,200\n"
    )
    # "₹1,200" contains a comma, so it must be quoted in real CSV files.
    csv_text = csv_text.replace("₹1,200", '"₹1,200"')
    assert dues_for(csv_text)["D"].outstanding == 1000


@pytest.mark.parametrize(
    "bad, fragment",
    [
        ("", "empty"),
        ("name,when\nA,1\n", "Missing column"),
        ("customer,date,type,amount\nA,notadate,credit,10\n", "Line 2"),
        ("customer,date,type,amount\nA,2026-10-01,gift,10\n", "type must be"),
        ("customer,date,type,amount\nA,2026-10-01,credit,-5\n", "greater than zero"),
        ("customer,date,type,amount\nA,2026-10-01,credit,abc\n", "amount"),
        ("customer,date,type,amount\n,2026-10-01,credit,5\n", "customer name"),
    ],
)
def test_bad_input_gives_readable_errors(bad, fragment):
    with pytest.raises(LedgerError) as err:
        parse_ledger(bad)
    assert fragment.lower() in str(err.value).lower()


def test_sample_ledger_loads_and_has_dues():
    with open("sample_data/khata.csv", encoding="utf-8") as fh:
        owing = customers_with_dues(compute_dues(parse_ledger(fh.read()), TODAY))
    names = [d.name for d in owing]
    assert "Priya Kulkarni" not in names  # fully paid
    assert names[0] == "Imran Shaikh"  # oldest unpaid credit
