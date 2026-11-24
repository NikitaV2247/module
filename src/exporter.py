# -*- coding: utf-8 -*-
"""Экспорт расписания в текстовые форматы (TXT и CSV)."""

from __future__ import annotations

import csv
import io

from src.abbreviations import display_name
from src.models import Lesson


def to_text(
    lessons: list[Lesson],
    title: str,
    subtitle: str = "",
    with_context: bool = False,
) -> str:
    """Форматирует список занятий в читаемый текст.

    with_context=True добавляет день недели и группу к каждой строке —
    используется в результатах поиска.
    """
    lines: list[str] = []
    if title:
        lines.append(title)
    if subtitle:
        lines.append(subtitle)
    if title or subtitle:
        lines.append("=" * 52)
    if not lessons:
        lines.append("Занятий нет.")
    for l in lessons:
        room = f", каб. {l.room}" if l.room else ""
        teacher = f", преп. {l.teacher_label}" if l.teacher_label else ""
        ctx = f"[{l.day}, {l.group}] " if with_context else ""
        lines.append(
            f"{ctx}{l.number}. {l.time}  {display_name(l.subject)}{room}{teacher}"
        )
    return "\n".join(lines)


def to_csv(lessons: list[Lesson]) -> str:
    """Формирует CSV-таблицу занятий (разделитель — точка с запятой).

    В CSV пишется полное наименование дисциплины — как в данных
    учебного плана (краткие формы остаются для экранных представлений).
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(
        ["День", "Группа", "Пара", "Время", "Предмет", "Кабинет", "Преподаватель"]
    )
    for l in lessons:
        writer.writerow(
            [l.day, l.group, l.number, l.time, l.subject, l.room, l.teacher_label]
        )
    return buffer.getvalue()


def save_text(lessons: list[Lesson], path: str, title: str, subtitle: str = "") -> None:
    """Сохраняет текстовую карточку расписания в файл."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_text(lessons, title, subtitle))


def save_csv(lessons: list[Lesson], path: str) -> None:
    """Сохраняет CSV-файл с занятиями."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(to_csv(lessons))
