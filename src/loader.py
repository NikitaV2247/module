# -*- coding: utf-8 -*-
"""Загрузка данных модуля из JSON-файлов.

DataLoader        — готовое расписание недели (data/schedule.json);
CurriculumLoader  — учебный план: группы, дисциплины, часы, кабинеты
                    и сетка звонков по дням недели (data/curriculum.json,
                    секция 'bell_schedule');
save_schedule     — сохранение сгенерированного расписания обратно
                    в data/schedule.json в том же формате.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date

from src.models import (
    MAX_DAY_PAIRS,
    MAX_PAIRS,
    WEEKDAYS,
    Curriculum,
    Group,
    Lesson,
    Schedule,
    Subject,
    TimeSlot,
    apply_bell_schedule,
    day_pair_count,
    slots_for,
)


class DataLoader:
    """Загружает файл data/schedule.json и строит объект Schedule.

    Поднимает исключения:
        FileNotFoundError  — файл не найден;
        ValueError         — повреждена структура JSON.
    """

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, "data", "schedule.json")
        self.path = path

    def load(self) -> Schedule:
        """Читает JSON и возвращает расписание."""
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Файл расписания не найден: {self.path}")

        with open(self.path, encoding="utf-8") as f:
            raw = json.load(f)

        schedule_data = raw.get("schedule")
        if not isinstance(schedule_data, dict):
            raise ValueError("В файле расписания нет секции 'schedule'")

        schedule = Schedule(
            college=raw.get("college", ""),
            week=raw.get("week", ""),
            dates=raw.get("dates", {}),
        )

        for day, groups in schedule_data.items():
            for group_name, lessons in groups.items():
                group = schedule.group(group_name)
                if group is None:
                    group = Group(name=group_name)
                    schedule.groups.append(group)
                for number, info in lessons.items():
                    group.lessons.append(
                        Lesson(
                            day=day,
                            group=group.name,
                            number=int(number),
                            subject=info.get("subject", ""),
                            room=info.get("room", ""),
                            teacher=info.get("teacher", ""),
                        )
                    )
        return schedule

    @staticmethod
    def validate(schedule: Schedule) -> list[str]:
        """Простая валидация данных. Возвращает список проблем."""
        problems: list[str] = []
        per_day: dict[tuple[str, str], int] = {}
        day_numbers: dict[tuple[str, str], list[int]] = {}
        for group in schedule.groups:
            for lesson in group.lessons:
                if lesson.day not in WEEKDAYS:
                    problems.append(f"{group.name}: неизвестный день «{lesson.day}»")
                    continue
                limit = day_pair_count(lesson.day)
                if not 1 <= lesson.number <= limit:
                    problems.append(
                        f"{group.name}: {lesson.day}, пара {lesson.number} "
                        f"вне сетки звонков этого дня (1–{limit})"
                    )
                if not lesson.subject:
                    problems.append(f"{group.name}: пустой предмет")
                if isinstance(lesson.teacher, (list, tuple)):
                    problems.append(
                        f"{group.name}: {lesson.day}, пара {lesson.number} — "
                        "у занятия может быть только один преподаватель "
                        "(список в поле teacher недопустим)"
                    )
                elif lesson.teacher and not isinstance(lesson.teacher, str):
                    problems.append(
                        f"{group.name}: {lesson.day}, пара {lesson.number} — "
                        "некорректное поле teacher (ожидается строка)"
                    )
                key = (group.name, lesson.day)
                per_day[key] = per_day.get(key, 0) + 1
                day_numbers.setdefault(key, []).append(lesson.number)
        for (name, day), count in per_day.items():
            if count > MAX_DAY_PAIRS:
                problems.append(
                    f"{name}: {day} — {count} пар за день "
                    f"(максимум {MAX_DAY_PAIRS})"
                )
            numbers = sorted(day_numbers.get((name, day), []))
            missing = [
                n for n in range(numbers[0], numbers[-1] + 1) if n not in numbers
            ]
            if missing:
                missed = ", ".join(str(n) for n in missing)
                problems.append(
                    f"{name}: {day} — «окно» между парами: " f"пропущены пары {missed}"
                )
        return problems


_TIME_RE = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\s*[–—-]\s*(\d{1,2}):([0-5]\d)\s*$")


def parse_bell_schedule(raw) -> dict[str, list[TimeSlot]]:
    """Разбирает секцию 'bell_schedule' учебного плана.

    Формат: {«Понедельник»: {"1": "8:15–9:45", …}, …} — время пары
    целиком, «начало–конец». Возвращает словарь «день → список
    слотов» только для указанных дней (пары идут подряд с 1-й,
    по возрастанию времени). ValueError — при повреждённой
    структуре, неизвестном дне или некорректном времени.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Секция 'bell_schedule' должна быть словарём «день → пары»")
    grid: dict[str, list[TimeSlot]] = {}
    for day, pairs in raw.items():
        if day not in WEEKDAYS:
            raise ValueError(
                f"Неизвестный день «{day}» в 'bell_schedule' "
                f"(ожидается один из: {', '.join(WEEKDAYS)})"
            )
        if not isinstance(pairs, dict) or not pairs:
            raise ValueError(
                f"В 'bell_schedule' для «{day}» нет словаря пар «номер → время»"
            )
        slots: list[TimeSlot] = []
        for num, period in pairs.items():
            try:
                number = int(str(num).strip())
            except ValueError:
                raise ValueError(
                    f"Некорректный номер пары «{num}» в 'bell_schedule' "
                    f"для «{day}»: номер должен быть целым числом"
                ) from None
            if not 1 <= number <= MAX_PAIRS:
                raise ValueError(
                    f"Некорректный номер пары {num} в 'bell_schedule' "
                    f"для «{day}» (допустимо 1–{MAX_PAIRS})"
                )
            match = _TIME_RE.match(str(period))
            if not match:
                raise ValueError(
                    f"Некорректное время пары {num} для «{day}»: "
                    f"«{period}» (ожидается «8:15–9:45»)"
                )
            h1, m1, h2, m2 = (int(g) for g in match.groups())
            if h1 * 60 + m1 >= h2 * 60 + m2:
                raise ValueError(
                    f"Время пары {num} для «{day}»: начало не раньше конца "
                    f"(«{period}»)"
                )
            slots.append(
                TimeSlot(number=number, start=f"{h1}:{m1:02d}", end=f"{h2}:{m2:02d}")
            )
        slots.sort(key=lambda s: s.number)
        if [s.number for s in slots] != list(range(1, len(slots) + 1)):
            raise ValueError(
                f"В 'bell_schedule' для «{day}» пары должны идти подряд с 1-й "
                f"(получены: {', '.join(str(s.number) for s in slots)})"
            )
        starts = [s.start.split(":") for s in slots]
        minutes = [int(h) * 60 + int(m) for h, m in starts]
        if minutes != sorted(minutes):
            raise ValueError(
                f"В 'bell_schedule' для «{day}» пары не по возрастанию времени"
            )
        grid[day] = slots
    return grid


class CurriculumLoader:
    """Загружает учебный план data/curriculum.json.

    Помимо групп, дисциплин и периода семестра читает секцию
    'bell_schedule' — расписание звонков по дням недели («номер
    пары → время»). Указанные дни подменяют встроенную сетку
    (src.models.apply_bell_schedule), неуказанные — остаются
    со встроенными значениями.
    """

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, "data", "curriculum.json")
        self.path = path

    def load(self) -> Curriculum:
        """Читает JSON и возвращает учебный план."""
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Файл учебного плана не найден: {self.path}")

        with open(self.path, encoding="utf-8") as f:
            raw = json.load(f)

        subjects_raw = raw.get("subjects")
        groups_raw = raw.get("groups")
        if not isinstance(subjects_raw, list) or not isinstance(groups_raw, list):
            raise ValueError(
                "В учебном плане нет секций 'groups' и 'subjects' "
                "со списками групп и дисциплин"
            )
        if not groups_raw:
            raise ValueError("В учебном плане не указано ни одной группы")

        subjects: list[Subject] = []
        for item in subjects_raw:
            name = str(item.get("name", "")).strip()
            hours = int(item.get("hours", 0))
            rooms = tuple(
                str(r).strip() for r in item.get("rooms", []) if str(r).strip()
            )
            if not name or hours <= 0:
                raise ValueError(f"Некорректная дисциплина в учебном плане: {item}")
            raw_teacher = item.get("teacher", "")
            if isinstance(raw_teacher, (list, tuple)):
                raise ValueError(
                    f"У дисциплины «{name}» может быть только один "
                    "преподаватель (список в поле teacher недопустим)"
                )
            subjects.append(
                Subject(
                    name=name,
                    hours=hours,
                    rooms=rooms,
                    teacher=str(raw_teacher).strip(),
                )
            )

        semester_raw = raw.get("semester")
        if (
            not isinstance(semester_raw, dict)
            or not semester_raw.get("start")
            or not semester_raw.get("end")
        ):
            raise ValueError(
                "В учебном плане нет раздела 'semester' с датами начала и "
                "конца семестра (например, 2026-09-02 и 2026-12-20)"
            )
        try:
            start = date.fromisoformat(str(semester_raw["start"]))
            end = date.fromisoformat(str(semester_raw["end"]))
        except ValueError as e:
            raise ValueError(f"Некорректные даты семестра: {e}") from e
        if start > end:
            raise ValueError(
                "Начало семестра позже конца: "
                f"{start.isoformat()} > {end.isoformat()}"
            )

        # Расписание звонков по дням (секция 'bell_schedule'):
        # подменяет встроенную сетку для указанных дней
        bell_grid = parse_bell_schedule(raw.get("bell_schedule"))
        apply_bell_schedule(bell_grid)

        return Curriculum(
            college=raw.get("college", ""),
            start=start,
            end=end,
            groups=[str(g) for g in groups_raw],
            subjects=subjects,
            # снимок действующей сетки после применения секции
            bell_by_day={day: list(slots_for(day)) for day in WEEKDAYS},
        )


def save_schedule(schedule: Schedule, path: str) -> None:
    """Сохраняет расписание в формат data/schedule.json.

    Формат: дни → группы → номер пары → предмет, кабинет и
    преподаватель (если указан).
    """
    data: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for group in schedule.groups:
        for lesson in group.lessons:
            day_block = data.setdefault(lesson.day, {})
            group_block = day_block.setdefault(group.name, {})
            info: dict[str, str] = {
                "subject": lesson.subject,
                "room": lesson.room,
            }
            teacher = lesson.teacher_label
            if teacher:
                info["teacher"] = teacher
            group_block[str(lesson.number)] = info

    payload = {
        "college": schedule.college,
        "week": schedule.week,
        "days_order": WEEKDAYS,
        "dates": schedule.dates,
        "groups": schedule.group_names,
        "schedule": {day: data[day] for day in WEEKDAYS if day in data},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
