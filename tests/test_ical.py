# -*- coding: utf-8 -*-
"""Тесты экспорта в iCal (src/ical_export.py)."""

import pytest

from src.generator import ScheduleGenerator
from src.ical_export import _escape, _fold, lesson_event, save_ical, to_ical
from src.loader import DataLoader
from src.models import Schedule


@pytest.fixture(scope="module")
def app():
    schedule = DataLoader("data/schedule.json").load()
    gen = ScheduleGenerator(schedule)
    week = gen.group_week("4-1П9")
    lessons = [l for items in week.values() for l in items]
    return schedule, gen, week, lessons


def test_escape_and_fold():
    assert _escape("а, б; в") == "а\\, б\\; в"
    long = "x" * 200
    folded = _fold(long)
    assert all(len(line) <= 75 for line in folded.split("\r\n"))
    assert folded.split("\r\n")[1].startswith(" ")


def test_lesson_event_block(app):
    schedule, _gen, _week, lessons = app
    first = lessons[0]  # понедельник, 2-я пара (блок группы — 2–5)
    block = lesson_event(first, "2026-11-09")
    assert "BEGIN:VEVENT" in block
    assert "DTSTART:20261109T100500" in block
    assert "DTEND:20261109T114000" in block
    assert "SUMMARY:" in block
    assert "Группа 4-1П9 · 2-я пара" in block


def test_to_ical_full_week(app):
    schedule, _gen, _week, lessons = app
    text = to_ical(lessons, schedule)
    assert text.startswith("BEGIN:VCALENDAR")
    assert text.rstrip().endswith("END:VCALENDAR")
    # у группы 4-1П9 13 занятий — все в сетке звонков, пропусков нет
    assert text.count("BEGIN:VEVENT") == 13
    assert "X-SKIPPED-NO-TIME" not in text


def test_to_ical_without_dates_raises():
    empty = Schedule(college="К", week="нет дат", groups=[])
    with pytest.raises(ValueError, match="нет календарных дат"):
        to_ical([], empty)


def test_save_ical_file(app, tmp_path):
    schedule, _gen, _week, lessons = app
    path = tmp_path / "week.ics"
    save_ical(lessons, schedule, str(path))
    content = path.read_bytes()
    assert content.startswith(b"BEGIN:VCALENDAR")
    assert b"END:VCALENDAR" in content
    # CRLF-разделители по RFC 5545
    assert b"\r\n" in content


def test_event_description_contains_teacher(app):
    schedule, _gen, _week, lessons = app
    first = lessons[0]  # понедельник, 2-я пара: МДК 01.03, Козырев Д. А.
    block = lesson_event(first, "2026-11-09")
    assert "DESCRIPTION:" in block
    assert "преподаватель Козырев Д. А." in block
