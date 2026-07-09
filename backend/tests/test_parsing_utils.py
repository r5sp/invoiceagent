from datetime import date

import pytest

from app.services.parsing_utils import parse_currency, parse_date, parse_percent, parse_period_range


def test_parse_currency_basic():
    assert parse_currency("$45,500.00") == 45500.0
    assert parse_currency("$ 1,234.56") == 1234.56


def test_parse_currency_negative_parens():
    assert parse_currency("(38,500.00)") == -38500.0
    assert parse_currency("$ (38,500.00)") == -38500.0


def test_parse_currency_blank_dash():
    assert parse_currency("$-") == 0.0
    assert parse_currency("-") == 0.0
    assert parse_currency(None) is None


def test_parse_currency_ignores_trailing_junk():
    # A wrapped sentence fragment like "$700)" isn't a real amount — must not misparse as $700.
    assert parse_currency("$700)") is None


def test_parse_percent():
    assert parse_percent("184.6%") == pytest.approx(1.846)
    assert parse_percent("75%") == 0.75


def test_parse_date_formats():
    assert parse_date("7/3/2026") == date(2026, 7, 3)
    assert parse_date("4/6/26") == date(2026, 4, 6)
    assert parse_date("2026-04-06") == date(2026, 4, 6)


def test_parse_period_range_full_dates():
    start, end = parse_period_range("April 1 - June 30, 2026")
    assert start == date(2026, 4, 1)
    assert end == date(2026, 6, 30)


def test_parse_period_range_month_only():
    start, end = parse_period_range("April - June, 2026")
    assert start == date(2026, 4, 1)
    assert end == date(2026, 6, 30)
