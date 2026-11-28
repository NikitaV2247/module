# -*- coding: utf-8 -*-
"""Экспорт расписания в формат iCalendar (.ics, RFC 5545).
"""

from __future__ import annotations

from src.abbreviations import display_name
from src.models import Lesson, Schedule, time_slot

CAL_NAME = "Расписание занятий КПК"
PRODID = "-//KPC//Schedule Module 1.0//RU"


def _escape(text: str) -> str:
    """Экранирование спецсимволов iCal: ; , \\ и перевод строки."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Перенос строк длиннее 75 октетов (RFC 5545, 3.1)."""
    if len(line) <= 75:
        return line
    parts = [line[:74]]
    rest = line[74:]
    while rest:
        parts.append(" " + rest[:73])
        rest = rest[73:]
    return "\r\n".join(parts)


def _to_dt(date: str, hhmm: str) -> str:
    """«2026-10-05» + «8:15» → 20261005T081500."""
    d = date.replace("-", "")
    h, m = hhmm.split(":")
    return f"{d}T{int(h):02d}{int(m):02d}00"


def lesson_event(lesson: Lesson, date: str, uid_domain: str = "kpc-schedule") -> str:
    """Собирает блок VEVENT для одного занятия."""
    slot = time_slot(lesson.number, lesson.day)
    if slot is None:
        return ""  # пара вне сетки звонков дня — время не определено
    summary = display_name(lesson.subject)
    if lesson.room:
        summary += f" (каб. {lesson.room})"
    description = f"Группа {lesson.group} · {lesson.number}-я пара"
    if lesson.teacher_label:
        description += f" · преподаватель {lesson.teacher_label}"
    return "\r\n".join(
        [
            "BEGIN:VEVENT",
            f"UID:{_escape(lesson.group)}-{_escape(lesson.day)}-{lesson.number}@{uid_domain}",
            "DTSTAMP:20261104T000000Z",
            f"DTSTART:{_to_dt(date, slot.start)}",
            f"DTEND:{_to_dt(date, slot.end)}",
            f"SUMMARY:{_escape(summary)}",
            f"DESCRIPTION:{_escape(description)}",
            "END:VEVENT",
        ]
    )


def to_ical(lessons: list[Lesson], schedule: Schedule) -> str:
    """Собирает текст VCALENDAR для списка занятий.

    Занятия без определённого времени (вне сетки звонков) и дни
    без календарной даты пропускаются.
    """
    week_dates = schedule.week_dates
    if not week_dates:
        raise ValueError(
            "В данных расписания нет календарных дат недели — "
            "экспорт в iCal невозможен"
        )

    blocks: list[str] = []
    skipped = 0
    for lesson in lessons:
        date = week_dates.get(lesson.day, "")
        if not date:
            continue
        block = lesson_event(lesson, date)
        if block:
            blocks.append(block)
        else:
            skipped += 1

    header = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:{PRODID}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{_escape(CAL_NAME)}",
            f"X-WR-CALDESC:{_escape(schedule.college + ' · ' + schedule.week)}",
        ]
    )
    footer = "END:VCALENDAR"
    body = "\r\n".join(blocks)
    lines = [header]
    if body:
        lines.append(body)
    if skipped:
        # нестандартное свойство (RFC 5545 разрешает X-), внутри VCALENDAR
        lines.append(f"X-SKIPPED-NO-TIME:{skipped}")
    lines.append(footer)
    return _fold_all("\r\n".join(lines))


def _fold_all(text: str) -> str:
    """Применяет перенос строк ко всему календарю."""
    return "\r\n".join(_fold(line) for line in text.split("\r\n"))


def save_ical(lessons: list[Lesson], schedule: Schedule, path: str) -> None:
    """Сохраняет .ics-файл с расписанием."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(to_ical(lessons, schedule))
