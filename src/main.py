# -*- coding: utf-8 -*-
"""Консольный интерфейс модуля генерации расписания занятий.

Запуск:
    python -m src.main                            # интерактивное меню
    python -m src.main --generate                 # неделя с сегодняшней датой
    python -m src.main --generate --week 1        # 1-я неделя семестра
    python -m src.main --generate --week 2026-11-23   # неделя с датой
    python -m src.main --generate --day 2026-10-08    # один день
    python -m src.main --group 4-1П9 --day Понедельник
    python -m src.main --group 4-1П9 --week       # неделя с переменами
    python -m src.main --conflicts                # проверка конфликтов
    python -m src.main --group 4-1П9 --auto-schedule  # автогенерация недели группы
    python -m src.main --group 4-1П9 --auto-schedule --week 5  # на 5-ю неделю
    python -m src.main --search "МДК 02.02"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from src.conflicts import format_conflict_report
from src.exporter import save_csv, save_text, to_text
from src.generator import ScheduleGenerator
from src.html_export import save_html, save_week_html
from src.ical_export import save_ical
from src.loader import CurriculumLoader, DataLoader, save_schedule
from src.models import (
    MAX_DAY_PAIRS,
    WEEKDAYS,
    Group,
    Lesson,
    Schedule,
)
from src.pdf_export import save_week_pdf
from src.scheduler import (
    WeekScheduler,
    build_demands,
    build_schedule,
    format_generated_week,
)
from src.semester import Semester, SemesterWeek, parse_date


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schedule",
        description="Модуль генерации упрощённого расписания занятий КПК",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="собрать неделю (или один день) из учебного плана "
        "(data/curriculum.json) и сохранить в data/schedule.json",
    )
    parser.add_argument(
        "--out",
        metavar="FILE",
        help="куда сохранить сгенерированное расписание (по умолчанию data/schedule.json)",
    )
    parser.add_argument("--group", help="название группы, например 4-1П9")
    parser.add_argument(
        "--day",
        metavar="ДЕНЬ|ДАТА",
        help="с --group — день недели (Понедельник…Суббота) или дата "
        "(2026-10-08); с --generate — собрать расписание одного дня",
    )
    parser.add_argument(
        "--week",
        nargs="?",
        const="week",
        default=None,
        metavar="[НЕДЕЛЯ]",
        help="без значения и с --group — неделя группы; с --generate или "
        "--auto-schedule — номер недели семестра (1–16) или дата "
        "(2026-11-23), например --week 1 — 1-я неделя сентября",
    )
    parser.add_argument(
        "--conflicts", action="store_true", help="проверка конфликтов и ограничений"
    )
    parser.add_argument(
        "--auto-schedule",
        action="store_true",
        help="пересобрать неделю группы из учебного плана "
        "(data/curriculum.json) и сохранить в data/schedule.json; "
        "расстановка зависит от номера недели — у каждой недели своё "
        "расписание (--week НОМЕР|ДАТА, по умолчанию неделя из расписания)",
    )
    parser.add_argument("--search", help="поиск занятий по предмету")
    parser.add_argument("--export-html", metavar="FILE", help="выгрузка в HTML")
    parser.add_argument("--export-csv", metavar="FILE", help="выгрузка в CSV")
    parser.add_argument("--export-txt", metavar="FILE", help="выгрузка в TXT")
    parser.add_argument("--export-ical", metavar="FILE", help="выгрузка в iCal (.ics)")
    parser.add_argument(
        "--export-pdf", metavar="FILE", help="выгрузка недели в PDF (A4)"
    )
    return parser


def resolve_day_name(value: str) -> str:
    """«Понедельник» или дата «2026-10-08» → название дня недели.

    ValueError — если строка не день недели и не дата, либо
    воскресенье (выходной день).
    """
    text = value.strip()
    if text in WEEKDAYS:
        return text
    try:
        d = parse_date(text)
    except ValueError as e:
        raise ValueError(
            f"Неизвестный день «{value}»: укажите день недели "
            f"({', '.join(WEEKDAYS)}) или дату (2026-10-08)"
        ) from e
    if d.weekday() >= len(WEEKDAYS):
        raise ValueError("Воскресенье — выходной день, занятий нет")
    return WEEKDAYS[d.weekday()]


def run_generate(
    out_path: str | None = None,
    week: str | None = None,
    day: str | None = None,
    seed_by_week: bool = False,
) -> int:
    """Собирает неделю или один день для всех групп из учебного плана.

    Период семестра задаётся в data/curriculum.json (2 сентября –
    20 декабря 2026 г., 16 недель). Что собрать:
        week=None, day=None — неделя из data/schedule.json (или
                              сегодняшняя, если расписание не читается);
        week="1"           — 1-я неделя сентября (номер 1–16);
        week="2026-11-23"   — неделя, содержащая дату (4-я неделя ноября);
        day="2026-10-08"    — один день (четверг 8 октября).

    Часы дисциплин делятся на недели семестра, пары концентрируются
    по 3–4 в день (у группы — не более 4) и расставляются по сетке
    звонков с выбором свободного кабинета.

    seed_by_week=True (пункт 7 меню) привязывает расстановку к номеру
    недели семестра: у каждой недели — своё расписание, повторный
    запуск той же недели даёт тот же результат. По умолчанию (CLI
    --generate) расстановка детерминирована, как и раньше.
    """
    try:
        curriculum = CurriculumLoader().load()
    except (FileNotFoundError, ValueError) as e:
        print(f"Не удалось загрузить учебный план: {e}")
        return 1

    semester = Semester(curriculum.start, curriculum.end)

    try:
        if day:
            week_obj, day_name = semester.day_for_date(parse_date(day))
            only_day: str | None = day_name
        elif week:
            week_obj = semester.resolve(week)
            only_day = None
        else:
            try:
                week_obj = _week_from_schedule(DataLoader().load(), semester)
            except (FileNotFoundError, ValueError):
                week_obj = semester.week_for_date(date.today())
            only_day = None
    except ValueError as e:
        print(f"Ошибка выбора недели: {e}")
        print(
            "Укажите неделю: --week НОМЕР (1–%d) или --week ДАТА "
            "(2026-11-23); либо один день: --day ДАТА" % len(semester.weeks)
        )
        return 1

    try:
        demands = build_demands(curriculum)
        lessons = WeekScheduler(
            days=list(week_obj.days),
            seed=week_obj.number if seed_by_week else None,
        ).generate(demands)
    except ValueError as e:
        print(f"Ошибка генерации: {e}")
        return 1

    if only_day:
        lessons = [l for l in lessons if l.day == only_day]
        title = semester.day_title(week_obj, only_day)
        dates = {only_day: week_obj.dates[only_day]}
    else:
        title = semester.week_title(week_obj)
        dates = dict(week_obj.dates)

    schedule = build_schedule(
        lessons, college=curriculum.college, week=title, dates=dates
    )

    if out_path is None:
        out_path = default_schedule_path()
    save_schedule(schedule, out_path)

    total_weeks = len(semester.weeks)
    if only_day:
        print(
            f"День собран из учебного плана: {title} "
            f"({week_obj.number}-я неделя из {total_weeks})"
        )
    else:
        print(f"Неделя собрана из учебного плана: {title} " f"(из {total_weeks})")
    print(curriculum.college)
    print("=" * 52)
    for name in schedule.group_names:
        g = schedule.group(name)
        days = len({l.day for l in g.lessons})
        print(f"  {name}: {g.total_lessons} пар, занятий в {days} дн.")
    print("-" * 52)
    print(
        f"Всего занятий: {len(lessons)}; у группы — не более "
        f"{MAX_DAY_PAIRS} пар в день (дни по 3–4 пары), кабинеты — "
        "с выбором свободного"
    )
    if seed_by_week:
        print(
            f"Расстановка привязана к неделе ({week_obj.number}-я): "
            "у каждой недели семестра — своё расписание."
        )
    print(f"Сохранено: {out_path}")
    return 0


def default_schedule_path() -> str:
    """Путь к data/schedule.json (рядом с пакетом src)."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "schedule.json")


def _canonical_group(names: list[str], group: str) -> str | None:
    """Каноническое имя группы: без учёта регистра и пробелов."""
    key = group.strip().lower().replace(" ", "")
    for name in names:
        if name.lower().replace(" ", "") == key:
            return name
    return None


def _clone_schedule(schedule: Schedule) -> Schedule:
    """Копия расписания: группы и списки занятий — новые.

    Сами занятия — неизменяемые Lesson, их можно разделять между
    копиями: при автогенерации заменяется только список занятий
    выбранной группы, остальные группы остаются как были.
    """
    clone = Schedule(
        college=schedule.college, week=schedule.week, dates=dict(schedule.dates)
    )
    for g in schedule.groups:
        clone.groups.append(Group(name=g.name, lessons=list(g.lessons)))
    return clone


def _week_from_schedule(schedule: Schedule, semester: Semester) -> SemesterWeek:
    """Неделя семестра для дат из schedule.json, иначе — текущая неделя."""
    week_dates = schedule.week_dates
    if week_dates:
        monday = min(date.fromisoformat(v) for v in week_dates.values())
        return semester.week_for_date(monday)
    return semester.week_for_date(date.today())


def run_auto_week(
    group: str,
    week: str | None = None,
    out_path: str | None = None,
    schedule: Schedule | None = None,
) -> tuple[list[Lesson], dict[str, list[Lesson]], Schedule]:
    """Автогенерация недели группы из учебного плана с записью в файл.

    Предметы, часы и кабинеты берутся из data/curriculum.json (не из
    текущих занятий группы), число пар в неделе — из объёма часов
    дисциплин. Расстановка зависит от номера недели семестра (seed),
    поэтому у каждой недели — своё расписание. Итог записывается в
    data/schedule.json: занятия группы заменяются на новые, подпись
    недели и даты дней обновляются (как в пункте 8), остальные группы
    остаются без изменений.

        week=None    — неделя из дат schedule.json (или текущая);
        week="5"     — 5-я неделя семестра;
        week="2026-11-23" — неделя, содержащая дату.

    Возвращает (занятия, занятия по дням, обновлённое расписание).
    ValueError — если группа не найдена или неделю не выбрать.
    """
    try:
        curriculum = CurriculumLoader().load()
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"Не удалось загрузить учебный план: {e}") from e
    semester = Semester(curriculum.start, curriculum.end)

    if schedule is None:
        try:
            schedule = DataLoader().load()
        except (FileNotFoundError, ValueError) as e:
            raise ValueError(f"Не удалось загрузить расписание: {e}") from e
    else:
        schedule = _clone_schedule(schedule)

    name = _canonical_group(curriculum.groups, group) or _canonical_group(
        schedule.group_names, group
    )
    if name is None:
        raise ValueError(
            f"Группа «{group}» не найдена ни в учебном плане, ни в расписании"
        )

    week_obj = (
        semester.resolve(week) if week else _week_from_schedule(schedule, semester)
    )

    demands = [d for d in build_demands(curriculum) if d.group == name]
    if not demands:
        raise ValueError(f"В учебном плане нет дисциплин для группы «{name}»")

    lessons = WeekScheduler(days=list(week_obj.days), seed=week_obj.number).generate(
        demands
    )

    target = schedule.group(name)
    if target is None:
        target = Group(name=name)
        schedule.groups.append(target)
    target.lessons = list(lessons)
    schedule.week = semester.week_title(week_obj)
    schedule.dates = dict(week_obj.dates)

    if out_path is None:
        out_path = default_schedule_path()
    save_schedule(schedule, out_path)

    week_lessons: dict[str, list[Lesson]] = {}
    for lesson in lessons:
        week_lessons.setdefault(lesson.day, []).append(lesson)
    return lessons, week_lessons, schedule


def run_cli(args, gen: ScheduleGenerator) -> int:
    """Однократный запуск с аргументами командной строки."""
    if args.conflicts:
        print(format_conflict_report(gen.schedule))
        return 0

    if args.week not in (None, "week") and not args.auto_schedule:
        print(
            "Номер или дата в --week используется вместе с --generate "
            "или --auto-schedule (сборка недели из учебного плана). "
            "Справка: --help"
        )
        return 1

    if not args.group and not args.search:
        print("Укажите --group ГРУППА и/или --search ЗАПРОС. Справка: --help")
        return 1

    week_mode = args.week == "week" or args.auto_schedule
    try:
        if args.search:
            lessons = gen.find_by_subject(args.search)
            title = f"Занятия по запросу «{args.search}» — найдено: {len(lessons)}"
            print(to_text(lessons, title, gen.schedule.college, with_context=True))
        elif args.auto_schedule:
            out_path = args.out or default_schedule_path()
            lessons, week_lessons, new_schedule = run_auto_week(
                args.group,
                week=args.week if args.week not in (None, "week") else None,
                out_path=out_path,
                schedule=gen.schedule,
            )
            gen.schedule = new_schedule
            print(format_generated_week(lessons, new_schedule.college))
            print(f"Неделя: {new_schedule.week}")
            print(f"Сохранено: {out_path} (расписание в памяти обновлено)")
            title = f"Неделя группы {args.group} из учебного плана (автогенерация)"
        elif args.week == "week":
            print(gen.format_group_week(args.group))
            week_lessons = gen.group_week(args.group)
            lessons = [l for items in week_lessons.values() for l in items]
            title = f"Расписание группы {args.group} на неделю"
        else:
            day = resolve_day_name(args.day or WEEKDAYS[0])
            card = gen.format_group_day(args.group, day)
            print(card)
            lessons = gen.group_day(args.group, day)
            title = f"Расписание группы {args.group} — {day}"
            week_lessons = {day: lessons}
    except ValueError as e:
        print(f"Ошибка: {e}")
        return 1

    if args.export_html:
        if week_mode and len(week_lessons) > 1:
            save_week_html(
                args.group,
                week_lessons,
                args.export_html,
                title=title,
                subtitle=gen.schedule.college,
                college=gen.schedule.college,
                week=gen.schedule.week,
                dates=gen.schedule.dates,
            )
        else:
            save_html(
                lessons,
                args.export_html,
                title=title,
                subtitle=gen.schedule.college,
                college=gen.schedule.college,
                week=gen.schedule.week,
            )
        print(f"HTML сохранён: {args.export_html}")
    if args.export_csv:
        save_csv(lessons, args.export_csv)
        print(f"CSV сохранён: {args.export_csv}")
    if args.export_txt:
        save_text(lessons, args.export_txt, title, gen.schedule.college)
        print(f"TXT сохранён: {args.export_txt}")
    if args.export_ical:
        save_ical(lessons, gen.schedule, args.export_ical)
        print(f"iCal сохранён: {args.export_ical}")
    if args.export_pdf:
        if not week_mode:
            print("--export-pdf работает вместе с --week / --auto-schedule")
            return 1
        save_week_pdf(
            args.group,
            week_lessons,
            args.export_pdf,
            college=gen.schedule.college,
            week=gen.schedule.week,
            dates=gen.schedule.dates,
        )
        print(f"PDF сохранён: {args.export_pdf}")
    return 0


def export_week_pdf(gen: ScheduleGenerator, group: str, path: str) -> str:
    """Экспортирует неделю группы в настоящий PDF-файл (альбомный A4).

    Имя файла без расширения дополняется «.pdf», каталог создаётся
    при необходимости. Возвращает путь к сохранённому файлу;
    ValueError — если группы нет в расписании.
    """
    week_lessons = gen.group_week(group)  # ValueError, если группы нет
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    save_week_pdf(
        group,
        week_lessons,
        path,
        college=gen.schedule.college,
        week=gen.schedule.week,
        dates=gen.schedule.dates,
    )
    return path


def run_menu(gen: ScheduleGenerator) -> None:
    """Интерактивное меню."""
    print("=== Модуль генерации расписания ===")
    print(gen.schedule.college, "· неделя:", gen.schedule.week)
    while True:
        print(
            "\n1 — расписание группы на день\n"
            "2 — расписание группы на неделю (с переменами)\n"
            "3 — сводная доска по всем группам на день\n"
            "4 — поиск занятий по предмету\n"
            "5 — экспорт недели группы в PDF\n"
            "6 — проверка конфликтов и ограничений\n"
            "7 — автогенерация недели всех групп из учебного плана "
            "(с записью в schedule.json)\n"
            "0 — выход"
        )
        choice = input("Выберите пункт меню: ").strip()

        if choice == "0":
            print("Работа завершена.")
            break
        elif choice == "1":
            group = input("Группа (например, 4-1П9): ").strip()
            day = input(f"День ({', '.join(WEEKDAYS)}) или дата (2026-10-08): ").strip()
            try:
                print(gen.format_group_day(group, resolve_day_name(day)))
            except ValueError as e:
                print(f"Ошибка: {e}")
        elif choice == "2":
            group = input("Группа: ").strip()
            try:
                print(gen.format_group_week(group))
            except ValueError as e:
                print(f"Ошибка: {e}")
        elif choice == "3":
            day = input(f"День ({', '.join(WEEKDAYS)}) или дата (2026-10-08): ").strip()
            try:
                board = gen.day_board(resolve_day_name(day))
                for group, lessons in board.items():
                    print(f"\n--- {group} ---")
                    print(to_text(lessons, ""))
            except ValueError as e:
                print(f"Ошибка: {e}")
        elif choice == "4":
            query = input("Что искать (например, МДК или физкультура): ").strip()
            lessons = gen.find_by_subject(query)
            print(to_text(lessons, f"Найдено занятий: {len(lessons)}"))
        elif choice == "5":
            group = input("Группа (например, 4-1П9): ").strip()
            default = os.path.join("exports", f"week_{group}.pdf")
            path_input = input(f"Куда сохранить PDF (Enter — {default}): ").strip()
            try:
                path = export_week_pdf(gen, group, path_input or default)
                size = os.path.getsize(path)
                print(
                    f"Готово: настоящий PDF-файл сохранён — "
                    f"{os.path.abspath(path)} ({size / 1024:.0f} КБ)"
                )
            except ValueError as e:
                print(f"Ошибка: {e}")
        elif choice == "6":
            print(format_conflict_report(gen.schedule))
        elif choice == "7":
            week_spec = input(
                "Неделя семестра: номер (1–16) или дата (2026-11-23). "
                "Enter — неделя из расписания: "
            ).strip()
            if (
                run_generate(
                    default_schedule_path(),
                    week=week_spec or None,
                    seed_by_week=True,
                )
                == 0
            ):
                # перечитываем сгенерированное расписание для меню
                try:
                    gen.schedule = DataLoader().load()
                    print("(расписание в памяти обновлено)")
                except (FileNotFoundError, ValueError):
                    pass
        else:
            print("Нет такого пункта, попробуйте ещё раз.")


def main() -> int:
    args = build_parser().parse_args()

    if args.generate:
        week_spec = args.week if args.week not in (None, "week") else None
        return run_generate(args.out, week=week_spec, day=args.day)

    try:
        schedule = DataLoader().load()
    except (FileNotFoundError, ValueError) as e:
        print(f"Не удалось загрузить расписание: {e}")
        return 1

    problems = DataLoader.validate(schedule)
    if problems:
        print("Предупреждения валидации:")
        for p in problems[:10]:
            print(" -", p)

    gen = ScheduleGenerator(schedule)

    if any(
        [
            args.group,
            args.search,
            args.conflicts,
            args.export_html,
            args.export_csv,
            args.export_txt,
            args.export_ical,
            args.export_pdf,
        ]
    ):
        return run_cli(args, gen)
    run_menu(gen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
