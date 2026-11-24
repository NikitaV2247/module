# -*- coding: utf-8 -*-
"""Тесты автогенерации расписания (src/scheduler.py)."""

import pytest

from src.loader import CurriculumLoader, DataLoader
from src.models import MAX_DAY_PAIRS, MAX_PAIRS, WEEKDAYS, day_pair_count, time_slot
from src.scheduler import (
    Demand,
    WeekScheduler,
    build_demands,
    build_schedule,
    format_generated_week,
)


@pytest.fixture(scope="module")
def curriculum():
    return CurriculumLoader("data/curriculum.json").load()


# ── Базовая генерация ──────────────────────────────────────


def test_basic_generation_invariants():
    """Нагрузка расставляется полностью: слоты в сетке, без дублей, детерминизм."""
    demands = [
        Demand(group="X", subject="Математика", rooms="101", count=3),
        Demand(group="X", subject="Физика", rooms="102", count=2),
    ]
    lessons = WeekScheduler().generate(demands)
    assert len(lessons) == 5
    # все слоты в сетке звонков, время определено; у группы нет дублей слота
    slots = [(l.day, l.number) for l in lessons]
    assert len(slots) == len(set(slots))
    assert all(time_slot(l.number) is not None for l in lessons)
    # генератор детерминирован: повторный запуск даёт ту же расстановку
    second = WeekScheduler().generate(demands)
    assert [(l.day, l.number, l.subject) for l in lessons] == [
        (l.day, l.number, l.subject) for l in second
    ]


def test_one_subject_per_day_rule():
    """Один предмет — максимум один раз в день у группы."""
    demands = [Demand(group="X", subject="Математика", count=6)]
    lessons = WeekScheduler().generate(demands)
    per_day: dict[str, set[str]] = {}
    for l in lessons:
        per_day.setdefault(l.day, set()).add(l.subject)
    assert all(len(subs) == 1 for subs in per_day.values())
    # 6 пар одного предмета раскидались ровно по одному на каждый день
    assert len(lessons) == 6
    assert sorted(l.day for l in lessons) == sorted(WEEKDAYS)


@pytest.mark.parametrize(
    "demands, match",
    [
        pytest.param(
            [Demand(group="X", subject="Математика", count=7)],
            "Не удалось расставить",
            id="overload-one-subject",
        ),
        pytest.param(
            [Demand(group="X", subject=f"Предмет{i}", count=4) for i in range(6)]
            + [Demand(group="X", subject="Лишний", count=1)],
            "вместимость",
            id="weekly-capacity",
        ),
    ],
)
def test_impossible_load_raises(demands, match):
    """Невозможная нагрузка (7 пар предмета или 25-я пара недели) — ValueError."""
    with pytest.raises(ValueError, match=match):
        WeekScheduler().generate(demands)


# ── Лимит пар в дне и сетка до 7-й пары ───────────────────


def test_day_limit_four_pairs_binds():
    """24 пары (6 предметов × 4) расставляются ровно по 4 в день."""
    demands = [Demand(group="X", subject=f"Предмет{i}", count=4) for i in range(6)]
    lessons = WeekScheduler().generate(demands)
    assert len(lessons) == 24
    per_day: dict[str, int] = {}
    for l in lessons:
        per_day[l.day] = per_day.get(l.day, 0) + 1
    assert set(per_day.values()) == {MAX_DAY_PAIRS}  # все дни ровно по 4


def test_pairs_can_stand_up_to_seventh():
    """Пары могут стоять вплоть до 7-й по времени (во вт–пт).

    7 групп, у каждой 4 пары одного предмета в одном кабинете,
    дни — вторник…пятница (в этих днях сетка по 7 пар): кабинет
    один, в слоте — одно занятие, поэтому группы раскладываются
    по «этажам» 1–7.
    """
    demands = [
        Demand(group=f"Группа {i}", subject="МДК", rooms="405", count=4)
        for i in range(1, 8)
    ]
    lessons = WeekScheduler(days=["Вторник", "Среда", "Четверг", "Пятница"]).generate(
        demands
    )
    assert len(lessons) == 28
    used_slots = sorted({l.number for l in lessons})
    assert used_slots == [1, 2, 3, 4, 5, 6, 7]  # заняты все этажи сетки
    assert all(l.number <= MAX_PAIRS for l in lessons)


def test_saturday_grid_stops_at_fourth_pair():
    """В субботу «этажи» заканчиваются 4-й парой: сетка дня — 4 пары.

    4 группы по одной паре одного предмета в одном кабинете, день —
    только суббота: ровно 4 слота. Пятой группы в субботу нет места —
    пары 5+ в субботу не появляются (ни в сетке кандидатов, ни в
    предварительной проверке вместимости).
    """
    demands = [
        Demand(group=f"Группа {i}", subject="МДК", rooms="405", count=1)
        for i in range(1, 5)
    ]
    lessons = WeekScheduler(days=["Суббота"]).generate(demands)
    assert sorted(l.number for l in lessons) == [1, 2, 3, 4]
    # 5 пар одной группе в субботу не хватает: сетка дня — 4 пары
    extra = [
        Demand(group="X", subject=f"Предмет{i}", rooms="405", count=1)
        for i in range(1, 6)
    ]
    with pytest.raises(ValueError, match="вместимость"):
        WeekScheduler(days=["Суббота"]).generate(extra)


# ── Вариативность по неделям (seed) ────────────────────────


def test_seed_controls_arrangement():
    """Тот же seed — то же расписание, разные seed — разные расстановки."""
    demands = [Demand(group="X", subject=f"Предмет{i}", count=2) for i in range(6)]

    def key(lessons):
        return sorted((l.day, l.number, l.subject) for l in lessons)

    first = WeekScheduler(seed=7).generate(demands)
    assert key(first) == key(WeekScheduler(seed=7).generate(demands))
    assert key(first) != key(WeekScheduler(seed=1).generate(demands))
    assert key(first) != key(WeekScheduler(seed=2).generate(demands))


def test_seeded_week_respects_limits(curriculum):
    """Генерация с seed: 13 пар группы, лимит дня и «один предмет в день»."""
    demands = [d for d in build_demands(curriculum) if d.group == "4-1П9"]
    for seed in (1, 2, 3, 7, 16):
        lessons = WeekScheduler(seed=seed).generate(demands)
        assert len(lessons) == 13
        assert len({l.subject for l in lessons}) == 8
        per_day: dict[str, list[str]] = {}
        for l in lessons:
            per_day.setdefault(l.day, []).append(l.subject)
        assert all(len(subs) <= MAX_DAY_PAIRS for subs in per_day.values())
        # один предмет — не более одного раза в день
        assert all(len(set(subs)) == len(subs) for subs in per_day.values())


def test_week_concentrates_pairs_in_few_days():
    """12 пар группы — 3 дня по 4 пары, а не 6 дней по 2.

    По заданию в расписании должны быть дни с 3–4 парами,
    а не равномерное «по 2 пары каждый день».
    """
    demands = [Demand(group="X", subject=f"Предмет{i}", count=2) for i in range(6)]
    lessons = WeekScheduler().generate(demands)
    per_day: dict[str, int] = {}
    for l in lessons:
        per_day[l.day] = per_day.get(l.day, 0) + 1
    # пары сконцентрированы в первых трёх днях — по 4 в день
    assert set(per_day) == {"Понедельник", "Вторник", "Среда"}
    assert set(per_day.values()) == {MAX_DAY_PAIRS}


# ── Концентрация пар по 3–4 в день ─────────────────────


def test_days_with_three_or_four_pairs(curriculum):
    """Неделя из учебного плана: 13 пар = 4 + 3 + 3 + 3 по дням.

    В расписании есть несколько дней с 3–4 парами, пятница
    и суббота свободны — а не «по 2 пары каждый день».
    """
    lessons = WeekScheduler().generate(build_demands(curriculum))
    per_day: dict[str, int] = {}
    for l in lessons:
        if l.group == "4-1П9":
            per_day[l.day] = per_day.get(l.day, 0) + 1
    assert per_day == {"Понедельник": 4, "Вторник": 3, "Среда": 3, "Четверг": 3}
    assert all(3 <= c <= MAX_DAY_PAIRS for c in per_day.values())


def test_partial_week_uses_available_days(curriculum):
    """1-я неделя семестра (со 2 сентября): пары только ср–сб."""
    demands = build_demands(curriculum)
    lessons = WeekScheduler(days=["Среда", "Четверг", "Пятница", "Суббота"]).generate(
        demands
    )
    days = {l.day for l in lessons}
    assert days == {"Среда", "Четверг", "Пятница", "Суббота"}
    per_day: dict[str, int] = {}
    for l in lessons:
        if l.group == "4-1П9":
            per_day[l.day] = per_day.get(l.day, 0) + 1
    assert per_day == {"Среда": 4, "Четверг": 3, "Пятница": 3, "Суббота": 3}


# ── Кабинеты и альтернативы ────────────────────────────────


def test_room_alternative_when_busy():
    """Занят кабинет — дисциплина уходит в следующий из списка.

    Группа A занимает единственный кабинет 408 во всех слотах 1;
    группа B с тем же предметом уходит в альтернативу 412.
    """
    demands = [
        Demand(group="A", subject="МДК", rooms=("408",), count=6),
        Demand(group="B", subject="МДК", rooms=("408", "412"), count=6),
    ]
    lessons = WeekScheduler().generate(demands)
    rooms_b = {l.room for l in lessons if l.group == "B"}
    assert rooms_b == {"412"}  # 408 всегда занят группой A
    # двух групп в одном кабинете в одном слоте нет
    seen = [(l.day, l.number, l.room) for l in lessons]
    assert len(seen) == len(set(seen))


def test_no_room_conflicts_between_groups():
    """В одном кабинете в одном слоте — только одна группа."""
    demands = [
        Demand(group="A", subject="Физика", rooms=("100", "200"), count=3),
        Demand(group="B", subject="Химия", rooms=("100", "300"), count=3),
        Demand(group="C", subject="Биология", rooms=("100",), count=3),
    ]
    lessons = WeekScheduler().generate(demands)
    seen: dict[tuple[str, int, str], str] = {}
    for l in lessons:
        key = (l.day, l.number, l.room)
        assert key not in seen, f"двое в кабинете {l.room}"
        seen[key] = l.group


# ── Генерация из учебного плана ────────────────────────────


def test_build_demands_from_curriculum(curriculum):
    """Учебный план разворачивается в 3 × 8 требований по 13 пар."""
    demands = build_demands(curriculum)
    assert len(demands) == 3 * 8
    per_group: dict[str, int] = {}
    for d in demands:
        per_group[d.group] = per_group.get(d.group, 0) + d.count
    assert set(per_group.values()) == {13}


def test_generated_college_week(curriculum):
    """Интеграция: неделя всего колледжа — 39 занятий без нарушений."""
    lessons = WeekScheduler().generate(build_demands(curriculum))
    assert len(lessons) == 39

    # у каждой группы — 13 пар и 8 дисциплин
    by_group: dict[str, list] = {}
    for l in lessons:
        by_group.setdefault(l.group, []).append(l)
    for group, items in by_group.items():
        assert len(items) == 13
        assert len({l.subject for l in items}) == 8

    # лимит пар в день и сетка звонков
    per_day: dict[tuple[str, str], int] = {}
    rooms: dict[tuple[str, int, str], str] = {}
    for l in lessons:
        assert 1 <= l.number <= MAX_PAIRS
        key = (l.group, l.day)
        per_day[key] = per_day.get(key, 0) + 1
        rkey = (l.day, l.number, l.room)
        assert rkey not in rooms, f"кабинет {l.room} занят дважды"
        rooms[rkey] = l.group
    assert all(c <= MAX_DAY_PAIRS for c in per_day.values())


def test_build_schedule_from_lessons(curriculum):
    """Из списка занятий собирается объект Schedule."""
    lessons = WeekScheduler().generate(build_demands(curriculum))
    schedule = build_schedule(
        lessons, college="КПК", week="тест", dates={"Понедельник": "09.11"}
    )
    assert set(schedule.group_names) == {"4-1П9", "4-2П9", "3-1П11"}
    # в понедельник у каждой группы по 4 пары — всего 12
    assert len(schedule.lessons_on("Понедельник")) == 12


def test_roundtrip_from_group_lessons():
    """Пересборка недели группы: объём нагрузки сохраняется."""
    schedule = DataLoader("data/schedule.json").load()
    g = schedule.group("4-1П9")
    demands = WeekScheduler.from_group_lessons(g.lessons)
    lessons = WeekScheduler().generate(demands)
    assert len(lessons) == len(g.lessons)
    # дисциплины и кабинеты сохранены
    assert {l.subject for l in lessons} == {l.subject for l in g.lessons}
    assert {l.room for l in lessons} == {l.room for l in g.lessons}


def test_format_generated_week_output(curriculum):
    lessons = WeekScheduler().generate(build_demands(curriculum))
    text = format_generated_week(lessons, "КПК")
    assert "Автогенерация" in text
    assert "ПОНЕДЕЛЬНИК" in text
    assert "8:15–9:45" in text  # время 1-й пары
    assert "не более 4 пар в день" in text  # ограничение в подвале


# ── Сетка звонков дня: суббота — максимум 4 пары; без «окон» ─────


def test_week_generation_invariants(curriculum):
    """Инварианты любой недели (16 seed + детерминированный режим):

    номера пар не выходят за сетку звонков своего дня (в субботу —
    максимум 4-я), пары группы в дне идут подряд, без «окон».
    """
    demands = build_demands(curriculum)
    for seed in (None, *range(1, 17)):
        lessons = WeekScheduler(seed=seed).generate(demands)
        per: dict[tuple[str, str], list[int]] = {}
        for l in lessons:
            assert 1 <= l.number <= day_pair_count(l.day), (seed, l)
            per.setdefault((l.group, l.day), []).append(l.number)
        for (group, day), numbers in per.items():
            numbers = sorted(numbers)
            assert numbers == list(
                range(numbers[0], numbers[-1] + 1)
            ), f"seed={seed}: «окно» у {group} в {day}: {numbers}"
        # в субботу пары 5+ не появляются ни при каком seed
        saturday = [l for l in lessons if l.day == "Суббота"]
        assert all(1 <= l.number <= 4 for l in saturday)


def test_generated_output_shows_day_grid_times(curriculum):
    """В выводе автогенерации время пар — по сетке своего дня."""
    lessons = WeekScheduler().generate(build_demands(curriculum))
    text = format_generated_week(lessons, "КПК")
    assert "12:40–14:15" in text  # 3-я пара понедельника (после «РоВ»)
    assert "12:15–13:50" in text  # 3-я пара вторника–пятницы
    assert "без «окон»" in text  # правило сплошных блоков в подвале


# ── v0.7.2: преподаватель в требованиях и занятиях ──────────


def test_build_demands_carry_teacher():
    curriculum = CurriculumLoader("data/curriculum.json").load()
    demands = build_demands(curriculum)
    assert all(d.teacher for d in demands)
    mdk = next(d for d in demands if d.subject.startswith("МДК 01.02"))
    assert mdk.teacher == "Смирнов А. В."


def test_generated_lessons_have_teacher():
    """Сгенерированные занятия несут преподавателя своей дисциплины."""
    from src.scheduler import WeekScheduler

    curriculum = CurriculumLoader("data/curriculum.json").load()
    lessons = WeekScheduler(seed=7).generate(build_demands(curriculum))
    assert lessons and all(l.teacher for l in lessons)
    by_subject: dict[str, set[str]] = {}
    for l in lessons:
        by_subject.setdefault(l.subject, set()).add(l.teacher)
    assert all(len(teachers) == 1 for teachers in by_subject.values())


def test_from_group_lessons_keeps_teacher():
    from src.models import Lesson
    from src.scheduler import WeekScheduler

    lessons = [
        Lesson("Понедельник", "A", 1, "Физика", "101", teacher="Иванов И. И."),
        Lesson("Вторник", "A", 2, "Физика", "101", teacher="Иванов И. И."),
        Lesson("Вторник", "A", 3, "Химия", "102"),
    ]
    demands = WeekScheduler.from_group_lessons(lessons)
    by_subject = {d.subject: d.teacher for d in demands}
    assert by_subject["Физика"] == "Иванов И. И."
    assert by_subject["Химия"] == ""
