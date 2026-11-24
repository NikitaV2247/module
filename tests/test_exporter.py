# -*- coding: utf-8 -*-
"""Тесты экспорта расписания в TXT, CSV и HTML."""

import pytest

from src.exporter import save_csv, save_text, to_csv, to_text
from src.generator import ScheduleGenerator
from src.html_export import save_html, save_week_html, to_html, to_week_html
from src.loader import DataLoader


@pytest.fixture(scope="module")
def lessons() -> list:
    gen = ScheduleGenerator(DataLoader("data/schedule.json").load())
    return gen.group_day("4-1П9", "Понедельник")


def test_to_text_contains_subjects(lessons):
    text = to_text(lessons, "Тест")
    assert "Тест" in text
    assert "МДК 01.02" in text  # краткое имя
    assert "10:05–11:40" in text  # 2-я пара понедельника по звонкам КПК


def test_to_text_empty_list():
    assert "Занятий нет" in to_text([], "Пусто")


def test_to_csv_header_and_rows(lessons):
    csv_text = to_csv(lessons)
    lines = csv_text.splitlines()
    assert lines[0] == "День;Группа;Пара;Время;Предмет;Кабинет;Преподаватель"
    assert "10:05–11:40" in lines[1]  # время 2-й пары
    assert len(lines) == 1 + len(lessons)
    assert "4-1П9" in lines[1]
    # в CSV — полное наименование дисциплины из учебного плана
    assert "МДК 01.03 Разработка мобильных приложений" in lines[1]


def test_save_text_and_csv(tmp_path, lessons):
    txt = tmp_path / "rasp.txt"
    csvf = tmp_path / "rasp.csv"
    save_text(lessons, str(txt), "Расписание")
    save_csv(lessons, str(csvf))
    assert txt.read_text(encoding="utf-8").startswith("Расписание")
    # строк в CSV: заголовок + по одной на каждое занятие
    assert csvf.read_text(encoding="utf-8-sig").count("\n") == len(lessons) + 1


def test_to_html_page(lessons):
    page = to_html(lessons, "Расписание 4-1П9", "Понедельник")
    assert page.startswith("<!DOCTYPE html>")
    assert "Расписание 4-1П9" in page
    assert "<table>" in page
    assert "МДК 01.02" in page
    assert "Костромской политехнический колледж" in page
    assert "10:05–11:40" in page  # время 2-й пары


def test_to_html_escapes_and_empty():
    page = to_html([], "Пусто", "тест")
    assert "Занятий нет" in page


def test_to_html_single_table(lessons):
    """На странице ровно одна таблица и один заголовок колонок."""
    page = to_html(lessons, "Расписание", "ПН")
    assert page.count("<table>") == 1
    assert page.count("</table>") == 1
    assert page.count("<th>Предмет</th>") == 1
    # <tr>: заголовок + по одной строке на занятие; лишних строк нет
    assert page.count("<tr>") == len(lessons) + 1


def test_save_html(tmp_path, lessons):
    f = tmp_path / "rasp.html"
    save_html(lessons, str(f), "Расписание", "ПН")
    assert f.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


# ── Недельный HTML ──────────────────────────────────────────


@pytest.fixture(scope="module")
def week():
    gen = ScheduleGenerator(DataLoader("data/schedule.json").load())
    return gen, gen.group_week("4-1П9")


def test_to_week_html_page(week):
    gen, week_lessons = week
    page = to_week_html(
        "4-1П9",
        week_lessons,
        title="Неделя 4-1П9",
        subtitle="КПК",
        dates=gen.schedule.dates,
    )
    assert page.startswith("<!DOCTYPE html>")
    # секции всех шести дней с датами (пт и сб — «занятий нет»)
    for day in ("ПОНЕДЕЛЬНИК", "СУББОТА"):
        assert day in page
    # даты дней — из data/schedule.json (без привязки к конкретной неделе)
    assert gen.schedule.dates["Понедельник"] in page
    assert gen.schedule.dates["Суббота"] in page
    # перемены между соседними парами показываются
    assert "перемена 20 мин" in page
    # пар без занятия («окно») на странице нет
    assert "окно" not in page
    # таблицы только у дней с занятиями: пн–чт
    assert page.count("<h2") == 6
    assert page.count("<table>") == 4
    # подпись с ограничением и дневными сетками звонков
    assert "не более 4 пар в день" in page
    assert "пн — 6 пар, вт–пт — 7, сб — 4" in page


def test_save_week_html_file(week, tmp_path):
    gen, week_lessons = week
    f = tmp_path / "week.html"
    save_week_html(
        "4-1П9",
        week_lessons,
        str(f),
        dates=gen.schedule.dates,
    )
    content = f.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")
    assert "окно" not in content  # пары без занятия не выводятся


# ── v0.7.2: преподаватель в TXT/CSV/HTML ────────────────────


def test_to_text_shows_teacher(lessons):
    text = to_text(lessons, "Тест")
    assert "преп. Смирнов А. В." in text
    assert "преп. Лебедева Т. Н." in text
    assert "преп. Гусев В. П." in text


def test_to_csv_teacher_column(lessons):
    lines = to_csv(lessons).splitlines()
    assert lines[1].endswith("Козырев Д. А.")


def test_html_shows_teacher(lessons):
    page = to_html(lessons, "Тест")
    assert "<th>Преподаватель</th>" in page
    assert "Смирнов А. В." in page


def test_week_html_shows_teacher(lessons):
    page = to_week_html("4-1П9", {"Понедельник": lessons})
    assert "<th>Преподаватель</th>" in page
    assert "Смирнов А. В." in page
