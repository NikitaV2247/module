# -*- coding: utf-8 -*-
"""Тесты загрузчиков данных: расписание и учебный план."""

import json
from datetime import date

import pytest

from src.loader import CurriculumLoader, DataLoader, save_schedule
from src.models import (
    Curriculum,
    Group,
    Lesson,
    Schedule,
    apply_bell_schedule,
    day_pair_count,
    time_slot,
)

DATA_PATH = "data/schedule.json"
CURRICULUM_PATH = "data/curriculum.json"


@pytest.fixture
def loader() -> DataLoader:
    return DataLoader(DATA_PATH)


@pytest.fixture
def schedule(loader: DataLoader) -> Schedule:
    return loader.load()


# ── Готовое расписание (data/schedule.json) ────────────────


def test_load_returns_schedule(schedule: Schedule):
    """Загрузка возвращает расписание с корректным названием колледжа."""
    assert isinstance(schedule, Schedule)
    assert "Костромской политехнический колледж" in schedule.college


def test_schedule_contains_three_groups(schedule: Schedule):
    """В расписании — три группы учебного плана."""
    assert set(schedule.group_names) == {"4-1П9", "4-2П9", "3-1П11"}


def test_schedule_covers_study_days(schedule: Schedule):
    """Занятия сконцентрированы в пн–чт (дни по 3–4 пары), пт и сб свободны."""
    days = {lesson.day for g in schedule.groups for lesson in g.lessons}
    assert days == {
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
    }


def test_group_lookup_case_insensitive(schedule: Schedule):
    """Поиск группы не зависит от регистра и пробелов."""
    assert schedule.group("4-1П9") is not None
    assert schedule.group(" 4-1 п9 ") is not None
    assert schedule.group("9-9X9") is None


def test_missing_file_raises(tmp_path):
    """Отсутствующий файл приводит к FileNotFoundError."""
    dl = DataLoader(str(tmp_path / "nope.json"))
    with pytest.raises(FileNotFoundError):
        dl.load()


def test_broken_structure_raises(tmp_path):
    """Файл без секции 'schedule' приводит к ValueError."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"college": "КПК"}), encoding="utf-8")
    dl = DataLoader(str(bad))
    with pytest.raises(ValueError):
        dl.load()


def test_validation_clean_data(schedule: Schedule):
    """Сгенерированные данные проходят валидацию без замечаний."""
    problems = DataLoader.validate(schedule)
    assert problems == []


def test_validation_catches_grid_and_window_problems(schedule: Schedule):
    """Валидатор: пара вне сетки дня (пн 8-я, сб 5-я) и «окно» 1-2-4."""
    schedule.groups[0].lessons.append(
        Lesson("Понедельник", schedule.groups[0].name, 8, "Лишняя пара")
    )
    schedule.groups[0].lessons.append(
        Lesson("Суббота", schedule.groups[0].name, 5, "Лишняя пара")
    )
    problems = DataLoader.validate(schedule)
    assert any("вне сетки" in p for p in problems)
    assert any("Суббота, пара 5" in p and "вне сетки" in p for p in problems)

    schedule.groups[0].lessons.extend(
        Lesson("Пятница", schedule.groups[0].name, n, f"Предмет {n}") for n in (1, 2, 4)
    )
    problems = DataLoader.validate(schedule)
    assert any("«окно»" in p and "Пятница" in p for p in problems)


def test_validation_catches_day_overload():
    """Пять пар в день у группы — замечание о превышении лимита."""
    sched = Schedule(college="Тест", week="")
    sched.groups.append(Group(name="X"))
    for n in range(1, 6):
        sched.groups[0].lessons.append(Lesson("Понедельник", "X", n, f"Предмет {n}"))
    problems = DataLoader.validate(sched)
    assert any("5 пар за день" in p for p in problems)


def test_save_and_reload_roundtrip(schedule: Schedule, tmp_path):
    """Сохранение и повторная загрузка не теряют занятия."""
    path = tmp_path / "saved.json"
    save_schedule(schedule, str(path))
    reloaded = DataLoader(str(path)).load()
    assert reloaded.group_names == schedule.group_names
    assert reloaded.lessons_on("Понедельник") == schedule.lessons_on("Понедельник")
    assert len(reloaded.groups[0].lessons) == len(schedule.groups[0].lessons)


# ── Учебный план (data/curriculum.json) ───────────────────


def test_curriculum_loads_groups_and_subjects():
    """В учебном плане — 3 группы, 8 дисциплин и период семестра."""
    curriculum = CurriculumLoader(CURRICULUM_PATH).load()
    assert isinstance(curriculum, Curriculum)
    assert curriculum.groups == ["4-1П9", "4-2П9", "3-1П11"]
    assert len(curriculum.subjects) == 8
    assert curriculum.start == date(2026, 9, 2)
    assert curriculum.end == date(2026, 12, 20)
    assert curriculum.semester_weeks == 16


def test_curriculum_subject_hours_and_rooms():
    """Часы и кабинеты дисциплин — как в задании."""
    curriculum = CurriculumLoader(CURRICULUM_PATH).load()
    by_name = {s.name: s for s in curriculum.subjects}

    mdk0102 = by_name["МДК 01.02 Поддержка и тестирование программных модулей"]
    assert mdk0102.hours == 68
    assert mdk0102.rooms == ("408", "412", "405", "406")

    phys = by_name["Физическая культура"]
    assert phys.hours == 40
    assert phys.rooms == ("спортзал",)

    mdk1101 = by_name["МДК 11.01 Технологии разработки и защиты баз данных"]
    assert mdk1101.rooms == ("408",)  # один кабинет — без альтернатив


def test_curriculum_hours_to_weekly_pairs():
    """Часы → пары в неделю: 1 пара = 2 ак. часа, семестр 16 недель."""
    curriculum = CurriculumLoader(CURRICULUM_PATH).load()
    by_name = {
        s.name: s.pairs_per_week(curriculum.semester_weeks) for s in curriculum.subjects
    }
    assert by_name["Физическая культура"] == 1  # 40 ч → 20 пар → ~1/нед
    assert by_name["Английский язык"] == 1  # 30 ч
    assert by_name["Менеджмент в профессиональной деятельности"] == 1  # 40 ч
    assert (
        by_name["МДК 01.02 Поддержка и тестирование программных модулей"] == 2
    )  # 68 ч
    assert by_name["МДК 01.03 Разработка мобильных приложений"] == 3  # 80 ч
    assert (
        by_name[
            "МДК 02.02 Инструментальные средства разработки программного обеспечения"
        ]
        == 2
    )  # 70 ч
    assert by_name["МДК 11.01 Технологии разработки и защиты баз данных"] == 2  # 70 ч
    assert by_name["Немецкий язык"] == 1  # 30 ч
    # суммарно у группы 13 пар в неделю (дни по 3–4 пары)
    assert sum(by_name.values()) == 13


def test_curriculum_missing_semester_raises(tmp_path):
    """Учебный план без периода семестра — ValueError."""
    bad = tmp_path / "nosemester.json"
    bad.write_text(
        json.dumps(
            {"groups": ["X"], "subjects": [{"name": "МДК", "hours": 68}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="semester"):
        CurriculumLoader(str(bad)).load()


def test_curriculum_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        CurriculumLoader(str(tmp_path / "nope.json")).load()


def test_curriculum_broken_structure_raises(tmp_path):
    """Файл без списков групп и дисциплин — ValueError."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"college": "КПК"}), encoding="utf-8")
    with pytest.raises(ValueError):
        CurriculumLoader(str(bad)).load()


def test_curriculum_bad_subject_raises(tmp_path):
    """Дисциплина без часов или названия — ValueError."""
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {"groups": ["X"], "subjects": [{"name": "Пусто", "hours": 0}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        CurriculumLoader(str(bad)).load()


# ── Сетка звонков по дням (секция 'bell_schedule' учебного плана) ──


def test_curriculum_loads_bell_schedule():
    """Сетка звонков по дням читается из учебного плана (zvonki.pdf)."""
    curriculum = CurriculumLoader(CURRICULUM_PATH).load()
    monday = curriculum.bell_by_day["Понедельник"]
    assert [s.number for s in monday] == [1, 2, 3, 4, 5, 6]
    assert monday[0].time == "8:15–9:45"
    assert monday[2].time == "12:40–14:15"  # после «Разговоров о важном»
    saturday = curriculum.bell_by_day["Суббота"]
    assert [s.number for s in saturday] == [1, 2, 3, 4]
    assert saturday[1].time == "10:00–11:35"
    # в сетке нет слота «Разговоры о важном» (пн 12:00–12:30)
    assert "12:00–12:30" not in [s.time for s in monday]


def test_bell_schedule_applies_to_models():
    """После загрузки плана модель показывает время пар по сетке дня."""
    CurriculumLoader(CURRICULUM_PATH).load()
    assert time_slot(3, "Понедельник").time == "12:40–14:15"
    assert time_slot(2, "Суббота").time == "10:00–11:35"
    assert day_pair_count("Суббота") == 4
    assert day_pair_count("Понедельник") == 6


def test_bell_schedule_missing_section_uses_default(tmp_path):
    """Учебный план без 'bell_schedule' — работает встроенная сетка."""
    data = {
        "groups": ["X"],
        "subjects": [{"name": "МДК", "hours": 68}],
        "semester": {"start": "2026-09-02", "end": "2026-12-20"},
    }
    path = tmp_path / "no_bells.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    curriculum = CurriculumLoader(str(path)).load()
    assert curriculum.bell_by_day["Понедельник"][0].time == "8:15–9:45"
    assert day_pair_count("Понедельник") == 6
    assert day_pair_count("Суббота") == 4


def test_bell_schedule_custom_day_overrides_only_it(tmp_path):
    """Секция с одним днём переопределяет только его, остальные — встроенные."""
    data = {
        "groups": ["X"],
        "subjects": [{"name": "МДК", "hours": 68}],
        "semester": {"start": "2026-09-02", "end": "2026-12-20"},
        "bell_schedule": {"Суббота": {"1": "9:00–10:30", "2": "10:40–12:10"}},
    }
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        curriculum = CurriculumLoader(str(path)).load()
        assert [s.time for s in curriculum.bell_by_day["Суббота"]] == [
            "9:00–10:30",
            "10:40–12:10",
        ]
        assert day_pair_count("Суббота") == 2  # переопределён
        assert day_pair_count("Понедельник") == 6  # остальной — встроенный
    finally:
        apply_bell_schedule(None)  # возврат к встроенной сетке


def test_bell_schedule_invalid_sections_raise(tmp_path):
    """Повреждённая секция 'bell_schedule' — ValueError (по одному случаю)."""
    base = {
        "groups": ["X"],
        "subjects": [{"name": "МДК", "hours": 68}],
        "semester": {"start": "2026-09-02", "end": "2026-12-20"},
    }
    cases = [
        (["Понедельник"], "bell_schedule"),  # секция — не словарь
        ({"Воскресенье": {"1": "8:15–9:45"}}, "Неизвестный день"),
        ({"Суббота": {"1": "8:15"}}, "Некорректное время"),
        ({"Суббота": {"1": "9:45–8:15"}}, "начало не раньше конца"),
        ({"Суббота": {"1": "8:15–9:45", "3": "10:00–11:30"}}, "подряд с 1-й"),
        ({"Суббота": {"9": "8:15–9:45"}}, "номер пары"),
    ]
    for bells, match in cases:
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps(dict(base, bell_schedule=bells), ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=match):
            CurriculumLoader(str(path)).load()


# ── v0.7.2: преподаватели (один на дисциплину/занятие) ──────


def test_teacher_loaded_from_schedule():
    schedule = DataLoader("data/schedule.json").load()
    teachers = {l.teacher for g in schedule.groups for l in g.lessons}
    assert "" not in teachers  # преподаватель есть у каждого занятия
    assert "Смирнов А. В." in teachers


def test_validate_rejects_bad_teacher():
    """Список или не-строка в поле teacher — замечание валидатора."""
    schedule = Schedule(college="", week="")
    schedule.groups.append(
        Group(
            name="X",
            lessons=[
                Lesson(
                    "Понедельник",
                    "X",
                    1,
                    "Предмет",
                    "101",
                    teacher=["Иванов", "Петров"],
                ),
                Lesson("Вторник", "X", 1, "Предмет", "101", teacher=42),
            ],
        )
    )
    problems = DataLoader.validate(schedule)
    assert any("только один преподаватель" in p for p in problems)
    assert any("некорректное поле teacher" in p for p in problems)


def test_curriculum_teacher_loaded():
    curriculum = CurriculumLoader("data/curriculum.json").load()
    by_name = {s.name: s.teacher for s in curriculum.subjects}
    assert by_name["Физическая культура"] == "Гусев В. П."
    assert all(by_name.values())  # у всех дисциплин указан преподаватель


def test_curriculum_teacher_list_rejected(tmp_path):
    raw = {
        "college": "К",
        "semester": {"start": "2026-09-02", "end": "2026-12-20"},
        "groups": ["A"],
        "subjects": [
            {
                "name": "Предмет",
                "hours": 30,
                "rooms": ["101"],
                "teacher": ["Иванов", "Петров"],
            }
        ],
    }
    path = tmp_path / "curriculum.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="только один преподаватель"):
        CurriculumLoader(str(path)).load()


def test_save_schedule_teacher_field(tmp_path):
    """save_schedule пишет поле teacher; пустое поле не добавляется."""
    schedule = Schedule(college="К", week="Неделя")
    schedule.groups.append(
        Group(
            name="4-1П9",
            lessons=[
                Lesson(
                    "Понедельник",
                    "4-1П9",
                    1,
                    "МДК 01.03 Разработка мобильных приложений",
                    "408",
                    teacher="Козырев Д. А.",
                ),
                Lesson("Вторник", "4-1П9", 1, "Предмет"),
            ],
        )
    )
    path = tmp_path / "out.json"
    save_schedule(schedule, str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    monday = data["schedule"]["Понедельник"]["4-1П9"]["1"]
    tuesday = data["schedule"]["Вторник"]["4-1П9"]["1"]
    assert monday["teacher"] == "Козырев Д. А."
    assert "teacher" not in tuesday
