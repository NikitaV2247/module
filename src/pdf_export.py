# -*- coding: utf-8 -*-
"""Экспорт недельного расписания в PDF (reportlab, landscape A4).
"""

from __future__ import annotations

import html
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table
from reportlab.platypus import TableStyle as RLTableStyle

from src.abbreviations import display_name
from src.models import WEEKDAYS, Lesson

_FONT_REGULAR = "DejaVuSans"
_FONT_BOLD = "DejaVuSans-Bold"

# Где искать шрифты: сначала каталог модуля, затем системные пути
_FONT_DIRS = [
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts"
    ),
    "/usr/share/fonts/truetype/dejavu",
]
_FONT_FILES = {
    _FONT_REGULAR: "DejaVuSans.ttf",
    _FONT_BOLD: "DejaVuSans-Bold.ttf",
}

_fonts_ready = False


def _register_fonts() -> None:
    """Регистрирует TTF-шрифты DejaVu в reportlab."""
    global _fonts_ready
    if _fonts_ready:
        return
    for name, filename in _FONT_FILES.items():
        for directory in _FONT_DIRS:
            path = os.path.join(directory, filename)
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(name, path))
                break
        else:
            raise FileNotFoundError(
                f"Шрифт {filename} не найден ни в assets/fonts, "
                "ни в системном каталоге DejaVu"
            )
    _fonts_ready = True


def _styles() -> dict[str, ParagraphStyle]:
    """Набор стилей абзацев для таблицы."""
    _register_fonts()
    return {
        "header": ParagraphStyle(
            "header",
            fontName=_FONT_BOLD,
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#1e3a5f"),
            alignment=1,
        ),
        "cell": ParagraphStyle(
            "cell",
            fontName=_FONT_REGULAR,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1f2937"),
        ),
        "cell_bold": ParagraphStyle(
            "cell_bold",
            fontName=_FONT_BOLD,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#2c5282"),
        ),
        "title": ParagraphStyle(
            "title",
            fontName=_FONT_BOLD,
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1e3a5f"),
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#475569"),
        ),
    }


def save_week_pdf(
    group: str,
    week_lessons: dict[str, list[Lesson]],
    path: str,
    college: str = "",
    week: str = "",
    dates: dict[str, str] | None = None,
) -> None:
    """Сохраняет PDF недельного расписания группы (альбомная A4)."""
    dates = dates or {}
    styles = _styles()
    _register_fonts()

    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Расписание группы {group} на неделю",
        author="Модуль генерации расписания КПК",
    )

    story = [
        Paragraph(f"Расписание группы {group} на неделю", styles["title"]),
        Spacer(1, 4),
        Paragraph(f"{college} · {week}", styles["subtitle"]),
        Spacer(1, 10),
    ]

    # Таблица: столбец «Пара» + 6 дней
    header = [Paragraph("Пара", styles["header"])]
    for day in WEEKDAYS:
        date = dates.get(day, "")
        header.append(
            Paragraph(
                f"{day.upper()}" + (f"<br/>{date}" if date else ""),
                styles["header"],
            )
        )


    max_pair = max(
        (l.number for items in week_lessons.values() for l in items),
        default=1,
    )
    rows: list[list] = [header]
    for number in range(1, max_pair + 1):
        row: list = [Paragraph(f"{number}", styles["cell_bold"])]
        for day in WEEKDAYS:
            by_number = {l.number: l for l in week_lessons.get(day, [])}
            lesson = by_number.get(number)
            if lesson is not None:
                subject = display_name(lesson.subject)
                meta = f"{lesson.time}"
                if lesson.room:
                    meta += f" · каб. {lesson.room}"
                cell = f"{subject}<br/><font size=7 color='#64748b'>{meta}</font>"
                if lesson.teacher_label:
                    cell += (
                        f"<br/><font size=7 color='#64748b'>преп. "
                        f"{html.escape(lesson.teacher_label)}</font>"
                    )
                row.append(Paragraph(cell, styles["cell"]))
            else:
                row.append(Paragraph("", styles["cell"]))
        rows.append(row)

    avail = doc.width
    first_col = 22 * mm
    day_col = (avail - first_col) / len(WEEKDAYS)
    table = Table(rows, colWidths=[first_col] + [day_col] * len(WEEKDAYS))
    table.setStyle(
        RLTableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )
    story.append(table)

    doc.build(story)
