# -*- coding: utf-8 -*-
"""Тесты консольного интерфейса (src/main.py)."""

import json
from datetime import date

import pytest

from src.generator import ScheduleGenerator
from src.loader import CurriculumLoader, DataLoader
from src.main import (
    build_parser,
    main,
    resolve_day_name,
    run_auto_week,
    run_cli,
    run_generate,
)


@pytest.fixture(scope="module")
def gen() -> ScheduleGenerator:
    return ScheduleGenerator(DataLoader("data/schedule.json").load())


def test_parser_defaults_and_flags():
    """Без аргументов — меню; --week без значения — неделя группы."""
    args = build_parser().parse_args([])
    assert args.group is None and args.day is None
    assert not args.week and not args.conflicts and not args.generate
    args = build_parser().parse_args(
        ["--group", "4-1П9", "--week", "--export-html", "x.html"]
    )
    assert args.group == "4-1П9" and args.week == "week"
    assert args.export_html == "x.html"


def test_parser_generate_selectors():
    """--generate с селектором недели/дня и путём --out разбирается."""
    args = build_parser().parse_args(["--generate", "--week", "1"])
    assert args.generate and args.week == "1"
    args = build_parser().parse_args(["--generate", "--week", "2026-11-23"])
    assert args.week == "2026-11-23"
    args = build_parser().parse_args(["--generate", "--day", "2026-10-08"])
    assert args.day == "2026-10-08" and args.week is None
    args = build_parser().parse_args(["--generate", "--out", "tmp.json"])
    assert args.generate and args.out == "tmp.json"


def test_run_cli_group_day(gen: ScheduleGenerator, capsys):
    """Карточка дня печатается, код возврата — 0."""
    args = build_parser().parse_args(["--group", "4-1П9", "--day", "Понедельник"])
    assert run_cli(args, gen) == 0
    out = capsys.readouterr().out
    assert "2 пара 10:05–11:40" in out
    assert "МДК 01.02" in out


def test_run_cli_unknown_group(gen: ScheduleGenerator, capsys):
    """Неизвестная группа — код 1 и сообщение об ошибке."""
    args = build_parser().parse_args(["--group", "9-9Z9", "--day", "Понедельник"])
    assert run_cli(args, gen) == 1
    assert "не найдена" in capsys.readouterr().out


def test_run_cli_requires_group(gen: ScheduleGenerator, capsys):
    """Без группы и поиска — подсказка и код 1."""
    args = build_parser().parse_args([])
    assert run_cli(args, gen) == 1
    assert "--help" in capsys.readouterr().out


def test_run_cli_conflicts(gen: ScheduleGenerator, capsys):
    """Отчёт о конфликтах печатается, код возврата — 0."""
    args = build_parser().parse_args(["--conflicts"])
    assert run_cli(args, gen) == 0
    out = capsys.readouterr().out
    assert "Конфликтов найдено: 5" in out
    assert "Конфликт преподавателя" in out
    assert "Нарушений ограничений: 0" in out


def test_run_cli_auto_schedule(gen: ScheduleGenerator, capsys, tmp_path):
    """Автогенерация недели группы: без недели (из расписания) и по номеру.

    --out указывает на временные файлы, чтобы не трогать
    data/schedule.json в репозитории.
    """
    out = tmp_path / "auto.json"
    args = build_parser().parse_args(
        ["--group", "4-1П9", "--auto-schedule", "--out", str(out)]
    )
    assert run_cli(args, gen) == 0
    captured = capsys.readouterr().out
    assert "Автогенерация" in captured
    assert "Сохранено" in captured
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert "неделя семестра" in saved["week"]
    assert saved["dates"]
    subjects = {
        info["subject"]
        for day in saved["schedule"].values()
        for info in day.get("4-1П9", {}).values()
    }
    curriculum = CurriculumLoader("data/curriculum.json").load()
    assert subjects == {s.name for s in curriculum.subjects}

    # --week 13 — неделя выбирается по номеру семестра
    out = tmp_path / "w13.json"
    args = build_parser().parse_args(
        ["--group", "4-2П9", "--auto-schedule", "--week", "13", "--out", str(out)]
    )
    assert run_cli(args, gen) == 0
    captured = capsys.readouterr().out
    assert "13-я неделя семестра" in captured
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["week"].endswith("13-я неделя семестра")
    assert saved["dates"]["Понедельник"] == "23.11"


def test_run_auto_week_builds_from_curriculum(tmp_path):
    """run_auto_week: предметы из учебного плана, файл записан."""
    out = tmp_path / "w5.json"
    base = DataLoader("data/schedule.json").load()
    old_week = base.week
    lessons, week_lessons, schedule = run_auto_week(
        "4-1П9", week="5", out_path=str(out), schedule=base
    )
    curriculum = CurriculumLoader("data/curriculum.json").load()
    assert len(lessons) == 13
    assert {l.subject for l in lessons} == {s.name for s in curriculum.subjects}
    assert schedule.week.endswith("5-я неделя семестра")
    # подпись недели и даты обновлены под выбранную неделю
    assert schedule.dates["Понедельник"] == "28.09"
    # исходное расписание не изменено: работа идёт с копией
    assert base.week == old_week
    assert len(base.group("4-1П9").lessons) == 13
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["week"].endswith("5-я неделя семестра")


def test_run_auto_week_other_groups_untouched(tmp_path):
    """Автогенерация меняет только выбранную группу в файле."""
    out = tmp_path / "only.json"
    run_auto_week("4-1П9", week="5", out_path=str(out))
    orig = DataLoader("data/schedule.json").load()
    reloaded = DataLoader(str(out)).load()

    def key(schedule, group):
        return {
            (l.day, l.number, l.subject, l.room) for l in schedule.group(group).lessons
        }

    for other in ("4-2П9", "3-1П11"):
        assert key(reloaded, other) == key(orig, other)


def test_run_auto_week_default_week_from_schedule(tmp_path):
    """Без недели берётся неделя из дат schedule.json (14–19.09 — 3-я)."""
    _, _, schedule = run_auto_week("3-1П11", out_path=str(tmp_path / "d.json"))
    assert schedule.week.endswith("3-я неделя семестра")


def test_run_auto_week_varies_between_weeks(tmp_path):
    """Разные недели — разные расстановки группы (содержимое файла новое)."""
    out5 = tmp_path / "w5.json"
    out6 = tmp_path / "w6.json"
    lessons5, _, _ = run_auto_week("4-1П9", week="5", out_path=str(out5))
    lessons6, _, _ = run_auto_week("4-1П9", week="6", out_path=str(out6))

    def key(lessons):
        return sorted((l.day, l.number, l.subject) for l in lessons)

    assert key(lessons5) != key(lessons6)
    saved5 = json.loads(out5.read_text(encoding="utf-8"))
    saved6 = json.loads(out6.read_text(encoding="utf-8"))
    assert saved5["week"] != saved6["week"]
    assert saved5["schedule"] != saved6["schedule"]


def test_run_auto_week_errors(tmp_path):
    """Ошибки автогенерации: группа не найдена; неделя вне семестра."""
    with pytest.raises(ValueError, match="не найдена"):
        run_auto_week("9-9Z9", week="5", out_path=str(tmp_path / "x.json"))
    with pytest.raises(ValueError, match="вне периода"):
        run_auto_week("4-1П9", week="2027-01-15", out_path=str(tmp_path / "x.json"))


def test_run_cli_search(gen: ScheduleGenerator, capsys):
    """Поиск по дисциплине печатается, код возврата — 0."""
    args = build_parser().parse_args(["--search", "МДК 02.02"])
    assert run_cli(args, gen) == 0
    assert "МДК 02.02" in capsys.readouterr().out


# ── Генерация недели из учебного плана ────────────────────


def test_run_cli_day_dates(gen: ScheduleGenerator, capsys):
    """День по дате: 2026-11-10 — вторник; воскресенье — выходной."""
    args = build_parser().parse_args(["--group", "4-1П9", "--day", "2026-11-10"])
    assert run_cli(args, gen) == 0
    assert "Вторник" in capsys.readouterr().out
    args = build_parser().parse_args(["--group", "4-1П9", "--day", "2026-11-15"])
    assert run_cli(args, gen) == 1
    assert "воскресенье" in capsys.readouterr().out.lower()


def test_resolve_day_name():
    """День недели или дата → название дня."""
    assert resolve_day_name("Понедельник") == "Понедельник"
    assert resolve_day_name("2026-10-08") == "Четверг"
    assert resolve_day_name("08.10.2026") == "Четверг"
    with pytest.raises(ValueError):
        resolve_day_name("2026-12-20")  # воскресенье
    with pytest.raises(ValueError):
        resolve_day_name("какой-то день")


def test_run_generate_saves_schedule(tmp_path, capsys):
    """--generate --week 11 собирает 39 занятий и сохраняет файл."""
    out = tmp_path / "generated.json"
    assert run_generate(str(out), week="11") == 0
    captured = capsys.readouterr().out
    assert "Неделя собрана из учебного плана" in captured
    assert "9–14 ноября 2026 г." in captured
    assert "Всего занятий: 39" in captured

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["college"] == "Костромской политехнический колледж"
    groups = {name for day in saved["schedule"].values() for name in day}
    assert groups == {"4-1П9", "4-2П9", "3-1П11"}
    # файл читается штатным загрузчиком
    reloaded = DataLoader(str(out)).load()
    assert len(reloaded.groups) == 3


def test_run_generate_week_by_number(tmp_path, capsys):
    """--generate --week 1 — 1-я неделя сентября, занятия со 2 сентября."""
    out = tmp_path / "w1.json"
    assert run_generate(str(out), week="1") == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["week"] == "2–5 сентября 2026 г. · 1-я неделя семестра"
    assert saved["dates"] == {
        "Среда": "02.09",
        "Четверг": "03.09",
        "Пятница": "04.09",
        "Суббота": "05.09",
    }
    # занятия только в учебных днях недели: среда … суббота
    assert set(saved["schedule"]) == {"Среда", "Четверг", "Пятница", "Суббота"}


def test_run_generate_week_by_date(tmp_path, capsys):
    """--generate --week 2026-11-23 — 4-я неделя ноября (13-я семестра)."""
    out = tmp_path / "w13.json"
    assert run_generate(str(out), week="2026-11-23") == 0
    captured = capsys.readouterr().out
    assert "23–28 ноября 2026 г." in captured
    assert "13-я неделя" in captured
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["dates"]["Понедельник"] == "23.11"


def test_run_generate_single_day(tmp_path, capsys):
    """--generate --day 2026-10-08 — расписание одного четверга."""
    out = tmp_path / "day.json"
    assert run_generate(str(out), day="2026-10-08") == 0
    captured = capsys.readouterr().out
    assert "Четверг, 8 октября 2026 г." in captured
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["week"] == "Четверг, 8 октября 2026 г."
    assert set(saved["schedule"]) == {"Четверг"}
    # в четверг у каждой группы по 3 пары
    total = sum(
        len(lessons)
        for groups in saved["schedule"].values()
        for lessons in groups.values()
    )
    assert total == 9


def test_run_generate_bad_period(tmp_path, capsys):
    """Дата вне периода семестра или воскресенье — код 1 и подсказка."""
    assert run_generate(str(tmp_path / "x.json"), week="2027-01-15") == 1
    out = capsys.readouterr().out
    assert "вне периода" in out
    assert "--week" in out
    assert run_generate(str(tmp_path / "x.json"), day="2026-12-20") == 1
    assert "воскресенье" in capsys.readouterr().out.lower()


def test_run_generate_overload_reports_error(tmp_path, capsys, monkeypatch):
    """Ошибка генерации (перегрузка) — код 1 и сообщение."""
    from src.loader import CurriculumLoader
    from src.models import Curriculum, Subject

    bad = Curriculum(
        college="Тест",
        start=date(2026, 9, 2),
        end=date(2026, 12, 20),
        groups=["X"],
        # 1000 часов за 16 недель → 31 пара в неделю — не влезет
        # в 6 дней × 4 пары = 24
        subjects=[Subject(name="МДК", hours=1000, rooms=("1",))],
    )
    monkeypatch.setattr(CurriculumLoader, "load", staticmethod(lambda self=None: bad))
    assert run_generate(str(tmp_path / "x.json"), week="1") == 1
    assert "Ошибка генерации" in capsys.readouterr().out


def test_run_generate_default_week_from_schedule(tmp_path, capsys):
    """--generate без --week: неделя берётся из дат schedule.json (3-я)."""
    out = tmp_path / "d.json"
    assert run_generate(str(out)) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["week"].endswith("3-я неделя семестра")
    assert saved["dates"]["Понедельник"] == "14.09"


def test_run_generate_seed_by_week(tmp_path):
    """seed_by_week: та же неделя — то же расписание, другие недели — другие."""
    out5a = tmp_path / "w5a.json"
    out5b = tmp_path / "w5b.json"
    out6 = tmp_path / "w6.json"
    assert run_generate(str(out5a), week="5", seed_by_week=True) == 0
    assert run_generate(str(out5b), week="5", seed_by_week=True) == 0
    assert run_generate(str(out6), week="6", seed_by_week=True) == 0
    week5a = json.loads(out5a.read_text(encoding="utf-8"))
    week5b = json.loads(out5b.read_text(encoding="utf-8"))
    week6 = json.loads(out6.read_text(encoding="utf-8"))
    assert week5a["schedule"] == week5b["schedule"]
    assert week5a["schedule"] != week6["schedule"]


def test_menu_item7_generates_all_groups(monkeypatch, capsys, tmp_path):
    """Пункт 7 меню: автогенерация недели всех групп с записью в файл.

    Пункт 8 в меню больше нет: input-последовательность не предполагает
    ни запроса группы, ни второго пункта.
    """
    import sys

    out = tmp_path / "menu.json"
    monkeypatch.setattr("src.main.default_schedule_path", lambda: str(out))
    answers = iter(["7", "5", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(sys, "argv", ["schedule"])
    assert main() == 0
    captured = capsys.readouterr().out
    assert "Неделя собрана из учебного плана" in captured
    assert "Расстановка привязана к неделе (5-я)" in captured
    assert "пункта, попробуйте ещё раз" not in captured
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["week"].endswith("5-я неделя семестра")
    groups = {name for day in saved["schedule"].values() for name in day}
    assert groups == {"4-1П9", "4-2П9", "3-1П11"}
    total = sum(
        len(lessons) for day in saved["schedule"].values() for lessons in day.values()
    )
    assert total == 39  # 3 группы × 13 пар


def test_main_generate_flag(monkeypatch, capsys, tmp_path):
    """python -m src.main --generate --week 13 --out FILE — код 0."""
    import sys

    out = tmp_path / "week.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["schedule", "--generate", "--week", "13", "--out", str(out)],
    )
    assert main() == 0
    assert out.exists()


def test_menu_exit(monkeypatch, capsys):
    """Меню: ввод «0» завершает работу с кодом 0."""
    import sys

    monkeypatch.setattr(sys, "argv", ["schedule"])
    monkeypatch.setattr("builtins.input", lambda _: "0")
    assert main() == 0
    assert "Работа завершена" in capsys.readouterr().out


# ── Пункт 5 меню: экспорт недели группы в PDF ───────────────


def test_menu_item5_pdf_paths(monkeypatch, capsys, tmp_path):
    """Пункт 5 сохраняет настоящий PDF: путь по умолчанию, авто-«.pdf», каталог."""
    import sys

    cases = [
        ("", tmp_path / "exports" / "week_4-1П9.pdf"),  # Enter — умолчание
        ("my_week", tmp_path / "my_week.pdf"),  # «.pdf» добавляется сама
        (
            str(tmp_path / "выгрузка" / "неделя.pdf"),
            tmp_path / "выгрузка" / "неделя.pdf",  # каталог создаётся
        ),
    ]
    for path_input, expected in cases:
        monkeypatch.chdir(tmp_path)
        answers = iter(["5", "4-1П9", path_input, "0"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        monkeypatch.setattr(sys, "argv", ["schedule"])
        assert main() == 0
        out = capsys.readouterr().out
        assert "PDF-файл сохранён" in out
        assert expected.exists()
        assert expected.read_bytes()[:5] == b"%PDF-"
        assert expected.stat().st_size > 10_000
        expected.unlink()


def test_menu_item5_unknown_group_keeps_menu_alive(monkeypatch, capsys, tmp_path):
    """Неизвестная группа — сообщение об ошибке, работа меню продолжается."""
    import sys

    monkeypatch.chdir(tmp_path)
    answers = iter(["5", "9-9Z9", "", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(sys, "argv", ["schedule"])
    assert main() == 0
    out = capsys.readouterr().out
    assert "Ошибка" in out
    assert "не найдена" in out
    assert "Работа завершена" in out  # меню дошло до выхода, не упало
    assert not (tmp_path / "exports").exists()  # файл не создавался
