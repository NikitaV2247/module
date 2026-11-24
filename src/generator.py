# -*- coding: utf-8 -*-
"""Генератор упрощённого расписания.

Превращает «сырые» данные расписания колледжа в удобные выборки:
по группе на день, по группе на неделю, сводную доску дня,
поиск по предмету и статистику.
"""

from __future__ import annotations

from src.abbreviations import display_name
from src.models import (
    BELL_SCHEDULE,
    MAX_DAY_PAIRS,
    MAX_PAIRS,
    WEEKDAYS,
    Lesson,
    Schedule,
    TimeSlot,
    break_after,
    slots_for,
)


class ScheduleGenerator:
    """Формирует упрощённые представления расписания."""

    def __init__(self, schedule: Schedule) -> None:
        self.schedule = schedule

    # ── Запросы ──────────────────────────────────────────────

    def group_day(self, group: str, day: str) -> list[Lesson]:
        """Занятия группы в конкретный день."""
        g = self.schedule.group(group)
        if g is None:
            raise ValueError(f"Группа «{group}» не найдена в расписании")
        if day not in WEEKDAYS:
            raise ValueError(f"День «{day}» не входит в учебную неделю")
        return g.lessons_on(day)

    def group_week(self, group: str) -> dict[str, list[Lesson]]:
        """Занятия группы на всю неделю: {день: [пары]}."""
        g = self.schedule.group(group)
        if g is None:
            raise ValueError(f"Группа «{group}» не найдена в расписании")
        return {day: g.lessons_on(day) for day in WEEKDAYS}

    def day_board(self, day: str) -> dict[str, list[Lesson]]:
        """Сводная доска дня: {группа: [пары]} для всех групп."""
        if day not in WEEKDAYS:
            raise ValueError(f"День «{day}» не входит в учебную неделю")
        board: dict[str, list[Lesson]] = {}
        for g in sorted(self.schedule.groups, key=lambda x: x.name):
            lessons = g.lessons_on(day)
            if lessons:
                board[g.name] = lessons
        return board

    def find_by_subject(self, query: str) -> list[Lesson]:
        """Поиск занятий по подстроке названия предмета.

        Поиск регистронезависимый, работает и по краткой форме
        («МДК 02.02»), и по полному названию дисциплины.
        """
        q = query.strip().lower()
        if not q:
            return []
        all_lessons: list[Lesson] = []
        for day in WEEKDAYS:
            all_lessons.extend(self.schedule.lessons_on(day))
        result = [
            lesson
            for lesson in all_lessons
            if q in f"{lesson.subject} {display_name(lesson.subject)}".lower()
        ]
        # сортировка: день недели по порядку, затем группа и номер пары
        return sorted(
            result,
            key=lambda l: (WEEKDAYS.index(l.day), l.group, l.number),
        )

    # ── Расписание звонков ─────────────────────────────────

    def time_slots(self, day: str | None = None) -> list[TimeSlot]:
        """Сетка звонков учебного дня (пн — 6 пар, вт–пт — 7, сб — 4).

        Без аргумента возвращается общая сетка недели (вт–пт, 7 пар).
        """
        return list(slots_for(day))

    # ── Статистика ───────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Краткая статистика по расписанию."""
        total = 0
        per_day: dict[str, int] = {}
        for day in WEEKDAYS:
            count = len(self.schedule.lessons_on(day))
            per_day[day] = count
            total += count
        return {
            "groups": len(self.schedule.groups),
            "total_lessons": total,
            **per_day,
        }

    # ── Упрощённые текстовые представления ───────────────────

    def format_group_day(self, group: str, day: str) -> str:
        """Текстовая карточка расписания группы на день.

        Выводятся только пары, на которые есть занятия, — с временем
        по звонкам. Пары без занятия не показываются: карточка
        остаётся короткой и отражает реальную нагрузку группы.
        """
        lessons = self.group_day(group, day)
        lines = [
            f"Расписание группы {group} — {day}",
            self.schedule.college,
            "=" * 64,
        ]
        if not lessons:
            lines.append("Занятий нет.")
        for l in lessons:
            room = f", каб. {l.room}" if l.room else ""
            teacher = f", преп. {l.teacher_label}" if l.teacher_label else ""
            lines.append(
                f"{l.number} пара {l.time}  {display_name(l.subject)}{room}{teacher}"
            )
        lines.append("=" * 64)
        return "\n".join(lines)

    # ── Генерация расписания на неделю ─────────────────────

    def format_group_week(self, group: str) -> str:
        """Недельное расписание группы с переменами между парами.

        В каждом дне показываются только занятия группы; между
        соседними парами — перемена по звонкам. Дни без занятий
        занимают одну строку. Пары без занятия («окна») не выводятся.
        """
        g = self.schedule.group(group)
        if g is None:
            raise ValueError(f"Группа «{group}» не найдена в расписании")

        dates = self.schedule.dates
        w = 64
        lines = [
            f"Расписание группы {group} на неделю",
            f"{self.schedule.college} · {self.schedule.week}",
            "=" * w,
        ]
        for day in WEEKDAYS:
            lessons = g.lessons_on(day)
            date_note = f" — {dates[day]}" if dates.get(day) else ""
            lines.append("")
            lines.append(f"{day.upper()}{date_note}")
            lines.append("-" * w)
            if not lessons:
                lines.append("  занятий нет")
            for i, l in enumerate(lessons):
                room = f" — каб. {l.room}" if l.room else ""
                teacher = f" — преп. {l.teacher_label}" if l.teacher_label else ""
                lines.append(
                    f"  {l.number} пара {l.time}  "
                    f"{display_name(l.subject)}{room}{teacher}"
                )
                nxt = lessons[i + 1] if i + 1 < len(lessons) else None
                if nxt is not None and nxt.number == l.number + 1:
                    lines.append(f"      · перемена {break_after(l.number, l.day)} мин")
        lines.append("-" * w)
        lines.append(
            f"У группы — не более {MAX_DAY_PAIRS} пар в день, без «окон» между "
            f"парами; сетка звонков: пн — 6 пар, вт–пт — {MAX_PAIRS}, сб — 4. "
            f"Перемены между парами (вт–пт): "
            + ", ".join(f"{break_after(s.number)} мин" for s in BELL_SCHEDULE[:-1])
            + "."
        )
        lines.append("=" * w)
        return "\n".join(lines)
