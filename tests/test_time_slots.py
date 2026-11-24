# -*- coding: utf-8 -*-
"""Тесты расписания звонков (сетка по дням: пн — 6, вт–пт — 7, сб — 4).

По заданию на модуль группа занимается максимум 4 пары в день,
но по времени пары могут стоять вплоть до последней пары дня.
Сетка звонков берётся из data/curriculum.json (секция
'bell_schedule', файл zvonki.pdf учебной части); «Разговоры
о важном» (пн 12:00–12:30) парой не является и в сетке отсутствует.
"""

import pytest

from src.generator import ScheduleGenerator
from src.loader import DataLoader
from src.models import (
    BELL_BY_DAY,
    BELL_SCHEDULE,
    MAX_DAY_PAIRS,
    MAX_PAIRS,
    Lesson,
    break_after,
    day_pair_count,
    slots_for,
    time_slot,
)


@pytest.fixture(scope="module")
def gen() -> ScheduleGenerator:
    return ScheduleGenerator(DataLoader("data/schedule.json").load())


def test_grid_counts_per_day():
    """В учебном дне разное число пар: пн — 6, вт–пт — 7, сб — 4."""
    assert [day_pair_count(d) for d in BELL_BY_DAY] == [6, 7, 7, 7, 7, 4]
    assert MAX_PAIRS == 7  # самая длинная сетка недели (вт–пт)
    assert [s.number for s in BELL_SCHEDULE] == [1, 2, 3, 4, 5, 6, 7]


def test_pair_times_by_day():
    """Время пар по дням: пн — 6 (без «РоВ»), вт–пт — 7, сб — 4."""
    assert [s.time for s in slots_for("Понедельник")] == [
        "8:15–9:45",
        "10:05–11:40",
        "12:40–14:15",
        "14:25–16:00",
        "16:10–17:45",
        "17:55–19:30",
    ]
    midweek = [
        "8:15–9:45",
        "10:05–11:40",
        "12:15–13:50",
        "14:00–15:35",
        "15:45–17:20",
        "17:30–19:05",
        "19:15–20:50",
    ]
    for day in ("Вторник", "Среда", "Четверг", "Пятница"):
        assert [s.time for s in slots_for(day)] == midweek
    assert [s.time for s in slots_for("Суббота")] == [
        "8:15–9:50",
        "10:00–11:35",
        "11:45–13:20",
        "13:30–15:05",
    ]


def test_grid_edges_and_razgovory():
    """Края сеток дня; «Разговоры о важном» (пн 12:00–12:30) — не пара."""
    assert time_slot(5, "Суббота") is None
    assert time_slot(4, "Суббота") is not None
    assert time_slot(7, "Понедельник") is None
    assert time_slot(6, "Понедельник") is not None
    assert time_slot(8) is None  # вне общей сетки
    assert time_slot(0) is None
    monday_times = [s.time for s in slots_for("Понедельник")]
    assert "12:00–12:30" not in monday_times
    for slots in BELL_BY_DAY.values():
        for s in slots:
            assert "Разговоры" not in s.time
    # после 2-й пары понедельника — большой перерыв до 3-й (12:40)
    assert break_after(2, "Понедельник") == 60


def test_breaks():
    """Перемены: общая сетка вт–пт и отличия по дням (пн — 60, сб — 10)."""
    assert [break_after(n) for n in range(1, 8)] == [20, 35, 10, 10, 10, 10, 0]
    assert break_after(2, "Понедельник") == 60  # 12:40 − 11:40
    assert break_after(1, "Суббота") == 10  # 10:00 − 9:50
    assert break_after(3, "Суббота") == 10
    assert break_after(4, "Суббота") == 0  # после 4-й пары субботы пар нет
    assert break_after(6, "Понедельник") == 0


def test_day_limit_is_four_pairs():
    """Максимум пар в дне у группы — 4 (по заданию на модуль)."""
    assert MAX_DAY_PAIRS == 4
    assert MAX_DAY_PAIRS <= day_pair_count("Суббота")  # сетка субботы — 4 пары


def test_lesson_time_uses_day_grid():
    """Lesson.time — по сетке своего дня; вне сетки — прочерк."""
    assert Lesson("Понедельник", "4-1П9", 3, "МДК 02.02", "405").time == "12:40–14:15"
    assert Lesson("Вторник", "4-1П9", 3, "МДК 02.02", "405").time == "12:15–13:50"
    assert Lesson("Суббота", "4-1П9", 2, "МДК 02.02", "405").time == "10:00–11:35"
    assert Lesson("Понедельник", "4-1П9", 6, "Физика").time == "17:55–19:30"
    assert Lesson("Вторник", "4-1П9", 6, "Физика").time == "17:30–19:05"
    assert Lesson("Суббота", "4-1П9", 5, "Физика").time == "—"
    assert Lesson("Суббота", "4-1П9", 8, "Физика").time == "—"


def test_generator_time_slots(gen: ScheduleGenerator):
    """ScheduleGenerator.time_slots: без дня — 7 пар, для субботы — 4."""
    slots = gen.time_slots()
    assert [s.number for s in slots] == [1, 2, 3, 4, 5, 6, 7]
    assert slots[1].time == "10:05–11:40"
    saturday = gen.time_slots("Суббота")
    assert [s.number for s in saturday] == [1, 2, 3, 4]
    assert saturday[0].time == "8:15–9:50"


def test_data_respects_day_grid_and_day_limit(gen: ScheduleGenerator):
    """Все занятия — в сетке звонков своего дня и ≤ 4 пар в день."""
    for g in gen.schedule.groups:
        assert all(1 <= l.number <= day_pair_count(l.day) for l in g.lessons)
        for day in {l.day for l in g.lessons}:
            assert len(g.lessons_on(day)) <= MAX_DAY_PAIRS
