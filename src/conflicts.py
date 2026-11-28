# -*- coding: utf-8 -*-
"""Проверка конфликтов расписания и учебных ограничений.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.abbreviations import display_name
from src.models import MAX_DAY_PAIRS, WEEKDAYS, Lesson, Schedule, day_pair_count

# Псевдо-аудитории: маркеры видов работы, а не кабинеты.
# Встречаются в расписании при ручном вводе; исключаются
# из проверки конфликтов аудиторий. Спортзал — настоящий кабинет
# (он один), поэтому конфликты в нём проверяются.
NON_ROOMS: frozenset[str] = frozenset({"ср", "экс"})

# Родительный падеж для заголовка конфликта
RESOURCE_DESCR = {
    "group": "группы",
    "room": "аудитории",
    "teacher": "преподавателя",
}


@dataclass(frozen=True)
class Conflict:
    """Один конфликт расписания.

    kind:      тип ресурса (group / room / teacher);
    day:       день недели;
    number:    номер пары;
    resource:  имя ресурса (название группы / кабинета / преподавателя);
    lessons:   конфликтующие занятия (не менее двух).
    """

    kind: str
    day: str
    number: int
    resource: str
    lessons: tuple[Lesson, ...] = field(default_factory=tuple)

    @property
    def title(self) -> str:
        who = RESOURCE_DESCR.get(self.kind, self.kind)
        when = f"{self.day}, {self.number}-я пара"
        return f"Конфликт {who} «{self.resource}» — {when}"

    @property
    def details(self) -> str:
        return "; ".join(
            f"{l.group}: {display_name(l.subject)} (каб. {l.room or '—'})"
            for l in self.lessons
        )


def _norm_room(raw: str) -> str:
    """Нормализация записи кабинета: « 212 » / «ср.» / «–/407» → ключ."""
    r = raw.replace("–", "-").replace("—", "-").strip()
    r = r.strip(" -.").strip()
    return r


def room_keys(lesson: Lesson) -> list[str]:
    """Ключи аудиторий занятия (подгруппы уже разбиты).

    Псевдо-аудитории («ср» — самостоятельная работа, «экс» —
    экскурсия, пустые и прочерковые записи) исключаются.
    """
    keys: list[str] = []
    for part in lesson.room.split("/"):
        r = _norm_room(part)
        if not r or r.lower() in NON_ROOMS:
            continue
        if r not in keys:
            keys.append(r)
    return keys


def _resource_key(lesson: Lesson, kind: str) -> str | None:
    """Ключ ресурса занятия или None, если ресурс не указан."""
    if kind == "group":
        return lesson.group
    if kind == "room":
        keys = room_keys(lesson)
        return keys[0] if len(keys) == 1 else None
    if kind == "teacher":
        return lesson.teacher_label or None
    return None


def find_conflicts(
    schedule: Schedule, kinds: tuple[str, ...] = ("group", "room", "teacher")
) -> list[Conflict]:
    """Ищет конфликты по выбранным типам ресурсов.

    """
    found: list[Conflict] = []
    for kind in kinds:
        # (день, номер, ресурс) -> [занятия]
        slots: dict[tuple[str, int, str], list[Lesson]] = defaultdict(list)
        for group in schedule.groups:
            for lesson in group.lessons:
                if kind == "room":
                    # подгруппы: каждая занимает свою аудиторию;
                    # псевдо-аудитории («ср», «экс») — не кабинеты
                    for k in room_keys(lesson):
                        slots[(lesson.day, lesson.number, k)].append(lesson)
                else:
                    key = _resource_key(lesson, kind)
                    if key is None:
                        continue
                    slots[(lesson.day, lesson.number, key)].append(lesson)
        for (day, number, resource), lessons in sorted(slots.items()):
            distinct = _distinct_sources(lessons, kind)
            if len(distinct) >= 2:
                found.append(
                    Conflict(
                        kind=kind,
                        day=day,
                        number=number,
                        resource=resource,
                        lessons=tuple(distinct),
                    )
                )
    return found


def lesson_has_data(kind: str, lesson: Lesson) -> bool:
    """Заполнено ли поле ресурса у занятия."""
    if kind == "room":
        return bool(room_keys(lesson))
    if kind == "teacher":
        return bool(lesson.teacher_label)
    return True


def _distinct_sources(lessons: list[Lesson], kind: str) -> list[Lesson]:
    """Отсечь дубли одной группы (для room — одна группа, два кабинета)."""
    if kind == "room":
        # разные группы в одном кабинете — конфликт; одна группа — нет
        seen_groups: dict[str, Lesson] = {}
        for l in lessons:
            if l.group not in seen_groups:
                seen_groups[l.group] = l
        return list(seen_groups.values())
    return lessons


@dataclass(frozen=True)
class ConstraintViolation:
    """Нарушение одного из учебных ограничений."""

    kind: str  # "time" | "window" | "load" | "format"
    message: str


def check_constraints(schedule: Schedule) -> list[ConstraintViolation]:
    """Проверяет временные и форматные ограничения.

    Временные: номер пары — в пределах сетки звонков своего дня
    (пн — 6, вт–пт — 7, сб — 4 пары). «Окна»: пары группы в учебном
    дне идут подряд, промежутки между ними не допускаются.
    Нагрузка: у группы не больше MAX_DAY_PAIRS (4) пар в день.
    Форматные: предмет непустой.
    """
    violations: list[ConstraintViolation] = []
    per_day: dict[tuple[str, str], int] = {}
    day_lessons: dict[tuple[str, str], list[Lesson]] = {}
    for group in schedule.groups:
        for lesson in group.lessons:
            if lesson.day in WEEKDAYS and not 1 <= lesson.number <= day_pair_count(
                lesson.day
            ):
                violations.append(
                    ConstraintViolation(
                        kind="time",
                        message=(
                            f"{group.name}: {lesson.day}, пара {lesson.number} "
                            f"вне сетки звонков этого дня "
                            f"(1–{day_pair_count(lesson.day)}) — "
                            f"{display_name(lesson.subject)}"
                        ),
                    )
                )
            if not lesson.subject.strip():
                violations.append(
                    ConstraintViolation(
                        kind="format",
                        message=f"{group.name}: пустой предмет ({lesson.day})",
                    )
                )
            key = (group.name, lesson.day)
            per_day[key] = per_day.get(key, 0) + 1
            day_lessons.setdefault(key, []).append(lesson)
    for (name, day), count in per_day.items():
        if count > MAX_DAY_PAIRS:
            violations.append(
                ConstraintViolation(
                    kind="load",
                    message=(
                        f"{name}: {day} — {count} пар за день "
                        f"(максимум {MAX_DAY_PAIRS})"
                    ),
                )
            )
        if day in WEEKDAYS:
            numbers = sorted(l.number for l in day_lessons.get((name, day), []))
            missing = [
                n for n in range(numbers[0], numbers[-1] + 1) if n not in numbers
            ]
            if missing:
                missed = ", ".join(str(n) for n in missing)
                violations.append(
                    ConstraintViolation(
                        kind="window",
                        message=(
                            f"{name}: {day} — «окно» между парами: "
                            f"пропущены пары {missed}"
                        ),
                    )
                )
    return violations


def format_conflict_report(schedule: Schedule) -> str:
    """Готовый текстовый отчёт о конфликтах и ограничениях."""
    lines = ["Проверка конфликтов и ограничений", "=" * 64]

    conflicts = find_conflicts(schedule)
    by_kind: dict[str, list[Conflict]] = defaultdict(list)
    for c in conflicts:
        by_kind[c.kind].append(c)

    lines.append(f"Конфликтов найдено: {len(conflicts)}")
    for c in conflicts:
        lines.append(f"  ! {c.title}: {c.details}")

    teachers_filled = any(l.teacher_label for g in schedule.groups for l in g.lessons)
    if not teachers_filled:
        lines.append(
            "  ~ преподаватели: в данных не указаны — проверка конфликтов "
            "преподавателей выполнена для пустого набора"
        )

    violations = check_constraints(schedule)
    lines.append(f"Нарушений ограничений: {len(violations)}")
    for v in violations:
        lines.append(f"  ? [{v.kind}] {v.message}")

    lines.append("=" * 64)
    return "\n".join(lines)
