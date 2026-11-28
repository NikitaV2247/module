# -*- coding: utf-8 -*-
"""Модели данных модуля генерации расписания занятий.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta



@dataclass(frozen=True)
class TimeSlot:
    """Временной слот одной пары.
    """

    number: int
    start: str
    end: str

    @property
    def time(self) -> str:
        """Время пары целиком: «8:15–9:45»."""
        return f"{self.start}–{self.end}"


def _grid(pairs: list[tuple[int, str, str]]) -> list[TimeSlot]:
    """Список (номер, начало, конец) → список TimeSlot."""
    return [TimeSlot(n, s, e) for n, s, e in pairs]


# Встроенная сетка звонков по дням недели (со стенда учебной части)
_DEFAULT_BELL_BY_DAY: dict[str, list[TimeSlot]] = {
    "Понедельник": _grid(
        [
            (1, "8:15", "9:45"),
            (2, "10:05", "11:40"),
            # «Разговоры о важном» (пн 12:00–12:30) — не пара, не в сетке
            (3, "12:40", "14:15"),
            (4, "14:25", "16:00"),
            (5, "16:10", "17:45"),
            (6, "17:55", "19:30"),
        ]
    ),
    "Вторник": _grid(
        [
            (1, "8:15", "9:45"),
            (2, "10:05", "11:40"),
            (3, "12:15", "13:50"),
            (4, "14:00", "15:35"),
            (5, "15:45", "17:20"),
            (6, "17:30", "19:05"),
            (7, "19:15", "20:50"),
        ]
    ),
    "Среда": _grid(
        [
            (1, "8:15", "9:45"),
            (2, "10:05", "11:40"),
            (3, "12:15", "13:50"),
            (4, "14:00", "15:35"),
            (5, "15:45", "17:20"),
            (6, "17:30", "19:05"),
            (7, "19:15", "20:50"),
        ]
    ),
    "Четверг": _grid(
        [
            (1, "8:15", "9:45"),
            (2, "10:05", "11:40"),
            (3, "12:15", "13:50"),
            (4, "14:00", "15:35"),
            (5, "15:45", "17:20"),
            (6, "17:30", "19:05"),
            (7, "19:15", "20:50"),
        ]
    ),
    "Пятница": _grid(
        [
            (1, "8:15", "9:45"),
            (2, "10:05", "11:40"),
            (3, "12:15", "13:50"),
            (4, "14:00", "15:35"),
            (5, "15:45", "17:20"),
            (6, "17:30", "19:05"),
            (7, "19:15", "20:50"),
        ]
    ),
    "Суббота": _grid(
        [
            (1, "8:15", "9:50"),
            (2, "10:00", "11:35"),
            (3, "11:45", "13:20"),
            (4, "13:30", "15:05"),
        ]
    ),
}

# Действующая сетка звонков по дням (подменяется из учебного плана)
BELL_BY_DAY: dict[str, list[TimeSlot]] = dict(_DEFAULT_BELL_BY_DAY)

# Общая (самая длинная) сетка недели — вт–пт; используется в легендах
BELL_SCHEDULE: list[TimeSlot] = BELL_BY_DAY["Вторник"]

# Сколько пар в самом длинном учебном дне по сетке звонков
MAX_PAIRS = len(BELL_SCHEDULE)

# Максимум пар в дне у одной группы (по заданию на модуль)
MAX_DAY_PAIRS = 4


def _to_minutes(hhmm: str) -> int:
    """«8:15» → 495 (минуты от полуночи)."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def apply_bell_schedule(grid: dict[str, list[TimeSlot]] | None) -> None:
    """Подменяет сетку звонков значениями из учебного плана.
    """
    global BELL_BY_DAY
    BELL_BY_DAY = dict(_DEFAULT_BELL_BY_DAY)
    for day, slots in (grid or {}).items():
        if day in BELL_BY_DAY and slots:
            BELL_BY_DAY[day] = list(slots)
    BELL_SCHEDULE[:] = BELL_BY_DAY["Вторник"]


def slots_for(day: str | None = None) -> list[TimeSlot]:
    """Сетка звонков дня недели; без дня — общая сетка (вт–пт)."""
    if day:
        slots = BELL_BY_DAY.get(day)
        if slots:
            return slots
    return BELL_SCHEDULE


def day_pair_count(day: str | None = None) -> int:
    """Сколько пар в учебном дне по сетке звонков (пн — 6, сб — 4)."""
    return len(slots_for(day))


def time_slot(number: int, day: str | None = None) -> TimeSlot | None:
    """Слот звонков для пары «номер» в сетке дня (1–7), либо None."""
    slots = slots_for(day)
    if 1 <= number <= len(slots):
        return slots[number - 1]
    return None


def break_after(number: int, day: str | None = None) -> int:
    """Перемена после пары «номер» в сетке дня, в минутах (0 — после последней)."""
    slots = slots_for(day)
    if not 1 <= number < len(slots):
        return 0
    cur = slots[number - 1]
    nxt = slots[number]
    return _to_minutes(nxt.start) - _to_minutes(cur.end)


# Дни учебной недели в порядке следования
WEEKDAYS: list[str] = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
]


@dataclass(frozen=True)
class Lesson:
    """Одно занятие (пара) в расписании.

    Атрибуты:
        day:     день недели («Понедельник» ... «Суббота»);
        group:   название группы (например, «4-1П9»);
        number:  номер пары (1–7, у группы — не более 4 в день);
        subject: предмет в сокращённой записи источника;
        room:    кабинет (может содержать «401/ср» для подгрупп);
        teacher: преподаватель (в текущих данных источника отсутствует,
                 поле зарезервировано для проверки конфликтов).
    """

    day: str
    group: str
    number: int
    subject: str
    room: str = ""
    teacher: str = ""

    @property
    def time(self) -> str:
        """Время пары по звонкам этого дня: «8:15–9:45»."""
        slot = time_slot(self.number, self.day)
        return slot.time if slot else "—"

    @property
    def subgroups(self) -> tuple[str, ...]:
        """Кортеж предметов по подгруппам.

        Запись «Стр.черчение/рисунок» означает, что 1-я подгруппа
        занимается черчением, а 2-я — рисунком.
        """
        parts = [p.strip() for p in self.subject.split("/")]
        return tuple(p for p in parts if p and p != "-")

    @property
    def rooms(self) -> tuple[str, ...]:
        """Кортеж кабинетов по подгруппам."""
        parts = [p.strip() for p in self.room.split("/")]
        return tuple(p for p in parts if p and p != "-")

    def __str__(self) -> str:
        room = f" (каб. {self.room})" if self.room else ""
        teacher = f", преп. {self.teacher_label}" if self.teacher_label else ""
        return f"{self.number} пара {self.time} — {self.subject}{room}{teacher}"

    @property
    def teacher_label(self) -> str:
        """Преподаватель одной строкой или «».
        """
        return self.teacher.strip() if isinstance(self.teacher, str) else ""


@dataclass(frozen=True)
class Subject:
    """Дисциплина учебного плана.
    """

    name: str
    hours: int
    rooms: tuple[str, ...] = ()
    teacher: str = ""

    @property
    def pairs_total(self) -> int:
        """Всего пар за семестр: 1 пара = 2 академических часа."""
        return self.hours // 2

    def pairs_per_week(self, weeks: int = 16) -> int:
        """Пар в неделю: часы / 2 / число недель семестра.
        """
        if weeks <= 0:
            raise ValueError("Число недель семестра должно быть положительным")
        return max(1, (self.hours + weeks) // (2 * weeks))


@dataclass
class Curriculum:
    """Учебный план: период семестра, группы и дисциплины.
    """

    college: str
    start: date
    end: date
    groups: list[str] = field(default_factory=list)
    subjects: list[Subject] = field(default_factory=list)
    # Сетка звонков по дням недели, загруженная из учебного плана
    # (секция 'bell_schedule'); пустой словарь — встроенная сетка.
    bell_by_day: dict[str, list[TimeSlot]] = field(default_factory=dict)

    @property
    def semester_weeks(self) -> int:
        """Число учебных недель в периоде семестра.
        """
        first_monday = self.start - timedelta(days=self.start.weekday())
        return (self.end - first_monday).days // 7 + 1


@dataclass
class Group:
    """Учебная группа и все её занятия за неделю."""

    name: str
    lessons: list[Lesson] = field(default_factory=list)

    def lessons_on(self, day: str) -> list[Lesson]:
        """Занятия группы в конкретный день, отсортированные по номеру пары."""
        return sorted(
            (l for l in self.lessons if l.day == day),
            key=lambda l: l.number,
        )

    @property
    def total_lessons(self) -> int:
        return len(self.lessons)


@dataclass
class Schedule:
    """Полное расписание колледжа за учебную неделю.
    """

    college: str
    week: str
    groups: list[Group] = field(default_factory=list)
    dates: dict[str, str] = field(default_factory=dict)

    @property
    def year(self) -> int | None:
        """Год учебной недели из строки «5–10 октября 2026 г.»."""
        m = re.search(r"(\d{4})", self.week)
        return int(m.group(1)) if m else None

    @property
    def week_dates(self) -> dict[str, str]:
        """Полные даты дней недели: {«Понедельник»: «2026-10-05», ...}."""
        if not self.dates or not self.year:
            return {}
        out: dict[str, str] = {}
        for day, ddmm in self.dates.items():
            d, m = ddmm.split(".")
            out[day] = f"{self.year}-{int(m):02d}-{int(d):02d}"
        return out

    def group(self, name: str) -> Group | None:
        """Поиск группы по названию."""
        for g in self.groups:
            if g.name.lower() == name.lower().replace(" ", ""):
                return g
        return None

    @property
    def group_names(self) -> list[str]:
        return sorted(g.name for g in self.groups)

    def lessons_on(self, day: str) -> list[Lesson]:
        """Все занятия колледжа в конкретный день."""
        result: list[Lesson] = []
        for g in self.groups:
            result.extend(g.lessons_on(day))
        return sorted(result, key=lambda l: (l.group, l.number))
