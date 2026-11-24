# -*- coding: utf-8 -*-
"""Тесты семестрового периода и выбора недели (src/semester.py)."""

from datetime import date

import pytest

from src.semester import Semester, parse_date


@pytest.fixture(scope="module")
def semester() -> Semester:
    # период семестра: 2 сентября 2026 (среда) — 20 декабря 2026 (воскресенье)
    return Semester(date(2026, 9, 2), date(2026, 12, 20))


# ── Недели периода ─────────────────────────────────────────


def test_semester_has_sixteen_weeks(semester: Semester):
    """В семестре 16 недель, нумерация сквозная 1–16."""
    assert len(semester.weeks) == 16
    assert [w.number for w in semester.weeks] == list(range(1, 17))


def test_first_week_starts_from_wednesday(semester: Semester):
    """1-я неделя начинается со среды 2 сентября — в ней четыре дня."""
    w1 = semester.week_by_number(1)
    assert w1.days == ("Среда", "Четверг", "Пятница", "Суббота")
    assert w1.dates == {
        "Среда": "02.09",
        "Четверг": "03.09",
        "Пятница": "04.09",
        "Суббота": "05.09",
    }
    assert w1.label == "2–5 сентября 2026 г."


def test_week_labels(semester: Semester):
    """Подписи недель: обычная, на стыке месяцев, первая и последняя."""
    w11 = semester.week_for_date(date(2026, 11, 10))
    assert w11.number == 11
    assert len(w11.days) == 6
    assert w11.label == "9–14 ноября 2026 г."
    assert w11.dates["Понедельник"] == "09.11"
    assert semester.week_by_number(5).label == "28 сентября – 3 октября 2026 г."
    w16 = semester.week_by_number(16)
    assert w16.label == "14–19 декабря 2026 г."
    assert w16.days[-1] == "Суббота"
    assert w16.dates["Суббота"] == "19.12"


# ── Выбор недели и дня ─────────────────────────────────────


def test_week_for_date_fourth_november_week(semester: Semester):
    """4-я неделя ноября (23–28 ноября) — это 13-я неделя семестра."""
    assert semester.week_for_date(date(2026, 11, 23)).number == 13
    assert semester.week_for_date(date(2026, 11, 26)).number == 13


def test_resolve_by_number_and_by_date(semester: Semester):
    """Неделя выбирается и по номеру, и по дате — результат один."""
    assert semester.resolve("13").number == 13
    assert semester.resolve("2026-11-23").number == 13
    assert semester.resolve("23.11.2026").number == 13
    assert semester.resolve("1").label == "2–5 сентября 2026 г."


def test_resolve_errors(semester: Semester):
    """Ошибки выбора недели: нет номера, вне периода, не дата, дата вне семестра."""
    with pytest.raises(ValueError):
        semester.resolve("17")  # недель всего 16
    with pytest.raises(ValueError):
        semester.resolve("2027-01-15")  # вне периода
    with pytest.raises(ValueError):
        semester.resolve("завтра")  # не дата и не номер
    with pytest.raises(ValueError, match="вне периода"):
        semester.week_for_date(date(2026, 8, 30))
    with pytest.raises(ValueError, match="вне периода"):
        semester.week_for_date(date(2026, 12, 21))


def test_day_for_date(semester: Semester):
    """8 октября 2026 — четверг 6-й недели; 20 декабря — выходной."""
    week, day = semester.day_for_date(date(2026, 10, 8))
    assert week.number == 6
    assert day == "Четверг"
    with pytest.raises(ValueError, match="воскресенье"):
        semester.day_for_date(date(2026, 12, 20))


# ── Подписи и разбор дат ───────────────────────────────────


def test_week_and_day_titles(semester: Semester):
    w13 = semester.week_by_number(13)
    assert semester.week_title(w13) == "23–28 ноября 2026 г. · 13-я неделя семестра"
    week, day = semester.day_for_date(date(2026, 10, 8))
    assert semester.day_title(week, day) == "Четверг, 8 октября 2026 г."


def test_parse_date_formats():
    assert parse_date("2026-10-08") == date(2026, 10, 8)
    assert parse_date("08.10.2026") == date(2026, 10, 8)
    with pytest.raises(ValueError):
        parse_date("8 октября")


def test_invalid_period_raises():
    with pytest.raises(ValueError, match="позже конца"):
        Semester(date(2026, 12, 20), date(2026, 9, 2))
