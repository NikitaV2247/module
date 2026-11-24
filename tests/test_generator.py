# -*- coding: utf-8 -*-
"""Тесты генератора расписания ScheduleGenerator."""

import pytest

from src.generator import ScheduleGenerator
from src.loader import DataLoader
from src.models import Lesson


@pytest.fixture(scope="module")
def gen() -> ScheduleGenerator:
    schedule = DataLoader("data/schedule.json").load()
    return ScheduleGenerator(schedule)


def test_group_day_returns_sorted_lessons(gen: ScheduleGenerator):
    """Понедельник, 4-1П9: 4 пары (2, 3, 4 и 5-я) подряд, по номеру."""
    lessons = gen.group_day("4-1П9", "Понедельник")
    assert [l.number for l in lessons] == [2, 3, 4, 5]
    assert lessons[0].subject == "МДК 01.03 Разработка мобильных приложений"
    assert lessons[0].room == "406"  # 405 занят другой группой — взята альтернатива
    assert lessons[1].room == "412"  # и у МДК 01.02 кабинет 408 занят → 412


def test_invalid_query_raises(gen: ScheduleGenerator):
    """Неизвестная группа или недоступный день — ValueError."""
    with pytest.raises(ValueError):
        gen.group_day("9-9Z9", "Понедельник")
    with pytest.raises(ValueError):
        gen.group_day("4-1П9", "Воскресенье")


def test_group_week_covers_all_days(gen: ScheduleGenerator):
    week = gen.group_week("4-1П9")
    assert len(week) == 6
    assert "Понедельник" in week and "Суббота" in week
    # у группы 13 занятий: пн 4 + вт 3 + ср 3 + чт 3
    assert sum(len(items) for items in week.values()) == 13


def test_day_board_contains_all_groups(gen: ScheduleGenerator):
    """Сводная доска дня содержит все три группы — по 4 пары."""
    board = gen.day_board("Понедельник")
    assert set(board) == {"4-1П9", "4-2П9", "3-1П11"}
    assert all(len(lessons) == 4 for lessons in board.values())


def test_find_by_subject_variants(gen: ScheduleGenerator):
    """Поиск: краткая и полная форма, регистр, пустой запрос."""
    by_short = gen.find_by_subject("МДК 02.02")
    by_full = gen.find_by_subject(
        "Инструментальные средства разработки программного обеспечения"
    )
    assert len(by_short) == 6  # 2 пары × 3 группы
    assert by_short == by_full
    # регистронезависимость: «физическая культура» — 3 занятия
    assert len(gen.find_by_subject("физическая культура")) == 3
    # пустой запрос — пустой результат
    assert gen.find_by_subject("   ") == []


def test_stats(gen: ScheduleGenerator):
    stats = gen.stats()
    assert stats["groups"] == 3
    assert stats["total_lessons"] == 39
    assert stats["Понедельник"] == 12  # 3 группы × 4 пары


def test_format_group_day_card(gen: ScheduleGenerator):
    """Карточка дня: только занятия, время по звонкам, краткое имя."""
    card = gen.format_group_day("4-1П9", "Понедельник")
    assert "4-1П9" in card
    assert "Понедельник" in card
    assert "2 пара 10:05–11:40" in card  # время по звонкам понедельника
    assert "МДК 01.02" in card  # краткое имя дисциплины
    assert "МДК 01.02 Поддержка" not in card  # полное имя — только в данных
    # пар без занятия в карточке нет: из сетки показаны 2, 3, 4 и 5-я
    assert "1 пара" not in card
    assert "6 пара" not in card
    assert "7 пара" not in card


def test_lesson_subgroups_parsing():
    """Запись «предмет1/предмет2» разбирается на подгруппы."""
    lesson = Lesson("Понедельник", "X", 1, "Черчение/рисунок", "220/226")
    assert lesson.subgroups == ("Черчение", "рисунок")
    assert lesson.rooms == ("220", "226")


# ── v0.7.2: преподаватель в текстовых карточках ─────────────


def test_texts_show_teacher(gen):
    """Преподаватель виден и в карточке дня, и в карточке недели."""
    assert "преп. Смирнов А. В." in gen.format_group_day("4-1П9", "Понедельник")
    assert "преп. Смирнов А. В." in gen.format_group_week("4-1П9")
