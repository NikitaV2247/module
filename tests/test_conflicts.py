# -*- coding: utf-8 -*-
"""Тесты проверки конфликтов и ограничений (src/conflicts.py)."""

import pytest

from src.conflicts import (
    check_constraints,
    find_conflicts,
    format_conflict_report,
    room_keys,
)
from src.loader import DataLoader
from src.models import Group, Lesson, Schedule


def _schedule(*lessons: Lesson) -> Schedule:
    groups: dict[str, Group] = {}
    for l in lessons:
        groups.setdefault(l.group, Group(name=l.group)).lessons.append(l)
    return Schedule(
        college="Тест",
        week="9–14 ноября 2026 г.",
        groups=list(groups.values()),
    )


@pytest.fixture(scope="module")
def real() -> Schedule:
    return DataLoader("data/schedule.json").load()


# ── Конфликты групп ─────────────────────────────────────────


def test_group_conflict_detected():
    """Одна группа в двух занятиях одновременно — конфликт."""
    sched = _schedule(
        Lesson("Понедельник", "X", 1, "Физика", "100"),
        Lesson("Понедельник", "X", 1, "Химия", "101"),
    )
    conflicts = find_conflicts(sched, kinds=("group",))
    assert len(conflicts) == 1
    assert conflicts[0].kind == "group"
    assert conflicts[0].title == "Конфликт группы «X» — Понедельник, 1-я пара"


def test_no_group_conflict_when_different_slots():
    """Разные слоты — конфликта нет."""
    sched = _schedule(
        Lesson("Понедельник", "X", 1, "Физика", "100"),
        Lesson("Понедельник", "X", 2, "Химия", "101"),
    )
    assert find_conflicts(sched, kinds=("group",)) == []


# ── Конфликты аудиторий ─────────────────────────────────────


def test_room_conflict_two_groups():
    """Две группы в одном кабинете одновременно — конфликт."""
    sched = _schedule(
        Lesson("Вторник", "A", 1, "Физика", "100"),
        Lesson("Вторник", "B", 1, "Химия", "100"),
    )
    conflicts = find_conflicts(sched, kinds=("room",))
    assert len(conflicts) == 1
    assert conflicts[0].resource == "100"
    assert len(conflicts[0].lessons) == 2


def test_gym_is_real_room():
    """Спортзал — настоящий кабинет: две группы сразу — конфликт."""
    sched = _schedule(
        Lesson("Пятница", "4-1П9", 2, "Физическая культура", "спортзал"),
        Lesson("Пятница", "4-2П9", 2, "Физическая культура", "спортзал"),
    )
    conflicts = find_conflicts(sched, kinds=("room",))
    assert len(conflicts) == 1
    assert conflicts[0].resource == "спортзал"


def test_room_pseudo_rooms_excluded():
    """«ср» (самостоятельная работа) и «экс» — не аудитории."""
    sched = _schedule(
        Lesson("Вторник", "A", 1, "Математика", "ср"),
        Lesson("Вторник", "B", 1, "История", "ср"),
        Lesson("Среда", "A", 1, "Экскурсия", "экс"),
        Lesson("Среда", "B", 1, "Экскурсия", "экс"),
    )
    assert find_conflicts(sched, kinds=("room",)) == []
    # ключи аудиторий пусты для псевдо-аудиторий
    lesson = Lesson("Вторник", "A", 1, "Математика", "ср")
    assert room_keys(lesson) == []


def test_room_subgroups_split():
    """Запись «314/307/407» — три аудитории, конфликт по совпадению."""
    sched = _schedule(
        Lesson("Понедельник", "A", 2, "Ин.язык", "314/307/407"),
        Lesson("Понедельник", "B", 2, "Ин.язык", "418/407"),
    )
    conflicts = find_conflicts(sched, kinds=("room",))
    assert [c.resource for c in conflicts] == ["407"]


def test_room_keys_normalization():
    """Прочерки, тире и точки нормализуются: «–/407» → 407."""
    lesson = Lesson("Вторник", "A", 2, "Ин.язык", "314/—407")
    assert room_keys(lesson) == ["314", "407"]
    lesson2 = Lesson("Вторник", "A", 2, "Ин.язык", " ср./ ср")
    assert room_keys(lesson2) == []


# ── Преподаватели ───────────────────────────────────────────


def test_teacher_conflict_when_data_present():
    """Если поле teacher заполнено — конфликт преподавателя ловится."""
    first = Lesson("Пятница", "A", 1, "Физика", "100", teacher="Иванов И.И.")
    second = Lesson("Пятница", "B", 1, "Астрономия", "102", teacher="Иванов И.И.")
    conflicts = find_conflicts(_schedule(first, second), kinds=("teacher",))
    assert len(conflicts) == 1
    assert conflicts[0].kind == "teacher"
    assert conflicts[0].resource == "Иванов И.И."


def test_teacher_conflicts_in_real_data(real: Schedule):
    """В демо-данных 5 конфликтов преподавателя (эксперимент v0.7.2).

    Один преподаватель на дисциплину: МДК 01.03 (Козырев Д. А.) идёт
    у трёх групп одновременно во вторник и среду, МДК 02.02
    (Фролова Е. А.) — во вторник и среду, МДК 01.02 (Смирнов А. В.) —
    в четверг.
    """
    conflicts = find_conflicts(real, kinds=("teacher",))
    assert len(conflicts) == 5
    assert {c.resource for c in conflicts} == {
        "Козырев Д. А.",
        "Фролова Е. А.",
        "Смирнов А. В.",
    }


# ── Сгенерированное расписание колледжа ────────────────────


def test_real_data_passes_all_checks(real: Schedule):
    """Демо-данные чисты: конфликтов нет, все ограничения соблюдены."""
    assert find_conflicts(real, kinds=("room",)) == []
    assert find_conflicts(real, kinds=("group",)) == []
    violations = check_constraints(real)
    assert [v for v in violations if v.kind in ("time", "load", "window")] == []


# ── Ограничения ─────────────────────────────────────────────


def test_constraint_violations_and_clean_block():
    """Нарушения: сетка дня, нагрузка, «окно»; сплошной блок пар — чист.

    Синтетические сценарии покрывают каждую ветку check_constraints:
    пара вне сетки субботы, 5 пар за день, пропущенная пара «1-2-4».
    """
    beyond = Lesson("Суббота", "Z", 5, "Алгебра", "1")
    violations = check_constraints(_schedule(beyond))
    time = [v for v in violations if v.kind == "time"]
    assert len(time) == 1
    assert "Суббота, пара 5" in time[0].message
    assert "вне сетки звонков этого дня (1–4)" in time[0].message

    lessons = [Lesson("Среда", "Z", n, f"Предмет {n}") for n in range(1, 6)]
    load = [v for v in check_constraints(_schedule(*lessons)) if v.kind == "load"]
    assert len(load) == 1
    assert "5 пар за день" in load[0].message

    lessons = [
        Lesson("Среда", "Z", 1, "Физика", "100"),
        Lesson("Среда", "Z", 2, "Химия", "100"),
        Lesson("Среда", "Z", 4, "Биология", "100"),
    ]
    windows = [v for v in check_constraints(_schedule(*lessons)) if v.kind == "window"]
    assert len(windows) == 1
    assert "«окно» между парами" in windows[0].message
    assert "пропущены пары 3" in windows[0].message

    # сплошной блок пар (2-3-4) — нарушение «окна» не регистрируется
    lessons = [
        Lesson("Среда", "Z", 2, "Физика", "100"),
        Lesson("Среда", "Z", 3, "Химия", "100"),
        Lesson("Среда", "Z", 4, "Биология", "100"),
    ]
    violations = check_constraints(_schedule(*lessons))
    assert [v for v in violations if v.kind == "window"] == []


# ── Отчёт ───────────────────────────────────────────────────


def test_conflict_report_text(real: Schedule):
    report = format_conflict_report(real)
    assert "Конфликтов найдено: 5" in report
    assert "Конфликт преподавателя" in report
    assert "Нарушений ограничений: 0" in report


# ── Ограничения: сетка дня и «окна» ──────────────────────────


def test_broken_teacher_data_does_not_crash():
    """Список в поле teacher не роняет проверку — конфликта нет."""
    lesson = Lesson("Понедельник", "A", 1, "Физика", "101", teacher=["Иванов"])
    schedule = Schedule(college="", week="")
    schedule.groups.append(Group(name="A", lessons=[lesson]))
    assert find_conflicts(schedule) == []
    report = format_conflict_report(schedule)
    assert "преподаватели: в данных не указаны" in report
