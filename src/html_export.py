# -*- coding: utf-8 -*-
"""Экспорт расписания в HTML-страницу."""

from __future__ import annotations

import html

from src.abbreviations import display_name
from src.models import BELL_SCHEDULE, MAX_DAY_PAIRS, WEEKDAYS, Lesson, break_after

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{
    font-family: "Segoe UI", Arial, sans-serif;
    background: #f0f4f8; color: #1f2937;
    margin: 0; padding: 32px 16px;
  }}
  .card {{
    max-width: 860px; margin: 0 auto;
    background: #ffffff; border-radius: 12px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, .08);
    overflow: hidden;
  }}
  .card-header {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
    color: #fff; padding: 24px 32px;
  }}
  .card-header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  .card-header p  {{ margin: 0; opacity: .85; font-size: 14px; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 14px;
  }}
  th {{
    text-align: left; padding: 10px 14px;
    background: #e8eef5; color: #1e3a5f;
    border-bottom: 2px solid #cbd5e1;
  }}
  td {{
    padding: 10px 14px; border-bottom: 1px solid #eef2f6;
    vertical-align: top;
  }}
  tr:nth-child(even) td {{ background: #f8fafc; }}
  .num {{
    display: inline-block; min-width: 26px; text-align: center;
    font-weight: 600; color: #2c5282;
    background: #e8eef5; border-radius: 6px; padding: 2px 6px;
  }}
  .room {{ color: #64748b; white-space: nowrap; }}
  .empty {{ padding: 24px; text-align: center; color: #94a3b8; }}
  .footer {{
    padding: 14px 32px; color: #94a3b8; font-size: 12px;
    text-align: right;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="card-header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  {body}
  <div class="footer">{college} · учебная неделя {week}</div>
</div>
</body>
</html>
"""

WEEK_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{
    font-family: "Segoe UI", Arial, sans-serif;
    background: #f0f4f8; color: #1f2937;
    margin: 0; padding: 32px 16px;
  }}
  .card {{
    max-width: 860px; margin: 0 auto;
    background: #ffffff; border-radius: 12px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, .08);
    overflow: hidden;
  }}
  .card-header {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
    color: #fff; padding: 24px 32px;
  }}
  .card-header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  .card-header p  {{ margin: 0; opacity: .85; font-size: 14px; }}
  .week-body {{ padding: 8px 24px 16px; }}
  h2.day {{
    margin: 22px 0 10px; font-size: 16px; color: #1e3a5f;
    border-bottom: 2px solid #cbd5e1; padding-bottom: 6px;
  }}
  h2.day .date {{
    font-weight: 400; color: #64748b; font-size: 13px; margin-left: 8px;
  }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 14px;
  }}
  th {{
    text-align: left; padding: 8px 12px;
    background: #e8eef5; color: #1e3a5f;
    border-bottom: 2px solid #cbd5e1;
  }}
  td {{
    padding: 8px 12px; border-bottom: 1px solid #eef2f6;
    vertical-align: top;
  }}
  tr:nth-child(even) td {{ background: #f8fafc; }}
  .num {{
    display: inline-block; min-width: 26px; text-align: center;
    font-weight: 600; color: #2c5282;
    background: #e8eef5; border-radius: 6px; padding: 2px 6px;
  }}
  .room {{ color: #64748b; white-space: nowrap; }}
  tr.brk td {{
    background: #f1f5f9 !important; color: #94a3b8;
    font-size: 12px; text-align: center; padding: 3px 12px;
  }}
  .empty-day {{
    color: #94a3b8; font-size: 13px; padding: 4px 2px 10px;
  }}
  .footer {{
    padding: 14px 32px; color: #94a3b8; font-size: 12px;
    text-align: right;
  }}
  .legend {{
    padding: 10px 24px 18px; color: #64748b; font-size: 12px;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="card-header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="week-body">
  {body}
  </div>
  <div class="legend">{legend}</div>
  <div class="footer">{college} · учебная неделя {week}</div>
</div>
</body>
</html>
"""


def lesson_row(lesson: Lesson) -> str:
    """HTML-строка таблицы для одного занятия."""
    subject = display_name(lesson.subject)
    room = html.escape(lesson.room) if lesson.room else "—"
    teacher = html.escape(lesson.teacher_label) if lesson.teacher_label else "—"
    return (
        f"<tr>"
        f'<td><span class="num">{lesson.number}</span></td>'
        f"<td>{lesson.time}</td>"
        f"<td>{html.escape(subject)}</td>"
        f'<td class="room">{room}</td>'
        f'<td class="room">{teacher}</td>'
        f"</tr>"
    )


def to_html(
    lessons: list[Lesson],
    title: str,
    subtitle: str = "",
    college: str = "Костромской политехнический колледж",
    week: str = "",
) -> str:
    """Собирает HTML-страницу с расписанием (только занятия)."""
    if lessons:
        rows = "\n".join(lesson_row(l) for l in lessons)
        table_header = (
            "<tr><th>№ пары</th><th>Время</th><th>Предмет</th><th>Кабинет</th>"
            "<th>Преподаватель</th></tr>"
        )
        body = "<table>\n" + table_header + "\n" + rows + "\n</table>"
    else:
        body = '<div class="empty">Занятий нет</div>'

    return PAGE_TEMPLATE.format(
        title=html.escape(title),
        subtitle=html.escape(subtitle),
        body=body,
        college=html.escape(college),
        week=html.escape(week),
    )


def save_html(
    lessons: list[Lesson],
    path: str,
    title: str,
    subtitle: str = "",
    college: str = "Костромской политехнический колледж",
    week: str = "",
) -> None:
    """Сохраняет HTML-страницу с расписанием в файл."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            to_html(
                lessons,
                title=title,
                subtitle=subtitle,
                college=college,
                week=week,
            )
        )


# ── Недельное расписание ──────────────────────────────────────


def _day_section(day: str, lessons: list[Lesson], date: str = "") -> str:
    """HTML-блок одного дня недельного расписания.

    Выводятся только занятия группы; между соседними парами —
    строка перемены. Пары без занятия не выводятся.
    """
    parts = [
        f'<h2 class="day">{html.escape(day.upper())}'
        + (f' <span class="date">{html.escape(date)}</span>' if date else "")
        + "</h2>"
    ]
    if not lessons:
        parts.append('<div class="empty-day">занятий нет</div>')
        return "\n".join(parts)

    rows: list[str] = []
    for i, l in enumerate(lessons):
        rows.append(lesson_row(l))
        nxt = lessons[i + 1] if i + 1 < len(lessons) else None
        if nxt is not None and nxt.number == l.number + 1:
            rows.append(
                f'<tr class="brk"><td colspan="5">перемена '
                f"{break_after(l.number, l.day)} мин</td></tr>"
            )
    parts.append(
        "<table>\n<tr><th>№ пары</th><th>Время</th><th>Предмет</th>"
        "<th>Кабинет</th><th>Преподаватель</th></tr>\n" + "\n".join(rows) + "\n</table>"
    )
    return "\n".join(parts)


def week_legend() -> str:
    """Подпись под недельным расписанием: сетка звонков и перемены."""
    pairs = " · ".join(f"{s.number}-я {s.time}" for s in BELL_SCHEDULE)
    brks = ", ".join(f"{break_after(s.number)} мин" for s in BELL_SCHEDULE[:-1])
    return (
        f"У группы — не более {MAX_DAY_PAIRS} пар в день, без «окон» между "
        f"парами. Сетка звонков: пн — 6 пар, вт–пт — {len(BELL_SCHEDULE)}, "
        f"сб — 4 (вт–пт: {pairs}). Перемены между парами (вт–пт): {brks}."
    )


def to_week_html(
    group: str,
    week_lessons: dict[str, list[Lesson]],
    title: str = "",
    subtitle: str = "",
    college: str = "Костромской политехнический колледж",
    week: str = "",
    dates: dict[str, str] | None = None,
) -> str:
    """Собирает HTML-страницу с расписанием группы на всю неделю."""
    dates = dates or {}
    sections = [
        _day_section(day, week_lessons.get(day, []), dates.get(day, ""))
        for day in WEEKDAYS
    ]
    body = "\n".join(sections)
    return WEEK_PAGE_TEMPLATE.format(
        title=html.escape(title or f"Расписание группы {group} на неделю"),
        subtitle=html.escape(subtitle),
        body=body,
        legend=html.escape(week_legend()),
        college=html.escape(college),
        week=html.escape(week),
    )


def save_week_html(
    group: str,
    week_lessons: dict[str, list[Lesson]],
    path: str,
    title: str = "",
    subtitle: str = "",
    college: str = "Костромской политехнический колледж",
    week: str = "",
    dates: dict[str, str] | None = None,
) -> None:
    """Сохраняет HTML-страницу недельного расписания в файл."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            to_week_html(
                group,
                week_lessons,
                title=title,
                subtitle=subtitle,
                college=college,
                week=week,
                dates=dates,
            )
        )
