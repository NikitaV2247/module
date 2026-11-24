# -*- coding: utf-8 -*-
"""Автогенерация расписания на неделю: жадный порядок + backtracking.

Алгоритм (упрощённый, учебный):
    1. Учебный план (Curriculum) разворачивается в требования Demand:
       часы дисциплины делятся на 2 (пара = 2 ак. часа) и на число
       недель семестра — так получается число пар в неделю
       (семестр 2 сентября – 20 декабря = 16 недель → у группы
       13 пар в неделю).
    2. Требования разворачиваются в отдельные пары-юниты и сортируются
       по убыванию объёма — «тяжёлые» дисциплины расставляются первыми.
    3. Для группы заранее считаются дневные лимиты: пары концентрируются
       в первых днях недели — дни заполняются до 4 пар, остаток даёт
       дни по 3 пары (13 пар = 4 + 3 + 3 + 3). Так в расписании есть
       несколько дней с 3–4 парами, а не «по 2 пары каждый день».
    4. Кандидаты-слоты перебираются по дням недели, внутри дня — по
       возрастанию номера пары. Номер пары ограничен сеткой звонков
       дня (пн — 6, вт–пт — 7, сб — 4 пары), поэтому в субботу пары
       выше 4-й не появляются. Пары группы в дне идут подряд, без
       «окон»: новая пара ставится только вплотную к уже стоящему
       блоку (перед ним или после него). Если слот занят (кабинет
       или сама группа), пара уходит на следующий номер — вплоть
       до последней пары дня.
    5. Кабинет для пары берётся первый свободный из списка дисциплины
       (например, МДК 01.02: 408 → 412 → 405 → 406) — это резервирование
       на случай, когда кабинет занят другой группой.
    6. Если юнит поставить нельзя, включается backtracking: последний
       поставленный юнит сдвигается на следующего кандидата.

Ограничения генератора:
    * у группы — не более MAX_DAY_PAIRS (4) пар в день;
    * слоты — в пределах сетки звонков своего дня (пн — 6, вт–пт — 7,
      сб — 4 пары); в субботу пары выше 4-й не появляются;
    * пары группы в дне идут подряд, без «окон» между ними;
    * один предмет — не более одного раза в день у группы;
    * один кабинет — одно занятие в слоте (между группами).

Вариативность по неделям:
    WeekScheduler(seed=...) включает случайную составляющую расстановки
    (порядок дисциплин, выбор дней и слотов, порядок кабинетов).
    Один и тот же seed даёт одно и то же расписание, поэтому в качестве
    seed удобно передавать номер недели семестра: у каждой недели —
    своя стабильная расстановка, у разных недель — разные.
    Без seed (seed=None) генератор полностью детерминирован, как и раньше.
"""

from __future__ import annotations

import random

from src.abbreviations import display_name
from src.models import (
    BELL_SCHEDULE,
    MAX_DAY_PAIRS,
    WEEKDAYS,
    Curriculum,
    Group,
    Lesson,
    Schedule,
    break_after,
    day_pair_count,
    time_slot,
)


def _as_rooms(rooms) -> tuple[str, ...]:
    """Нормализация списка кабинетов: строка → кортеж из одного."""
    if rooms is None:
        return ()
    if isinstance(rooms, str):
        return (rooms,) if rooms.strip() else ()
    return tuple(str(r).strip() for r in rooms if str(r).strip())


class Demand:
    """Требование к расписанию: дисциплине нужно `count` пар в неделю.

    Атрибуты:
        group:   группа;
        subject: дисциплина (полное наименование из учебного плана);
        rooms:   кабинеты в порядке предпочтения (если первый занят —
                 берётся следующий);
        teacher: преподаватель дисциплины (один, из учебного плана);
        count:   сколько пар в неделю нужно поставить.
    """

    def __init__(
        self,
        group: str,
        subject: str,
        rooms=(),
        teacher: str = "",
        count: int = 1,
    ) -> None:
        self.group = group
        self.subject = subject
        self.rooms = _as_rooms(rooms)
        self.teacher = teacher
        self.count = count

    def __repr__(self) -> str:
        return (
            f"Demand({self.group!r}, {self.subject!r}, "
            f"rooms={self.rooms!r}, teacher={self.teacher!r}, "
            f"count={self.count})"
        )


def build_demands(curriculum: Curriculum) -> list[Demand]:
    """Разворачивает учебный план в требования: часы → пары в неделю.

    Для каждой группы и каждой дисциплины считается число пар в неделю
    (Subject.pairs_per_week) и создаётся одно требование Demand.
    """
    demands: list[Demand] = []
    for group in curriculum.groups:
        for subject in curriculum.subjects:
            demands.append(
                Demand(
                    group=group,
                    subject=subject.name,
                    rooms=subject.rooms,
                    teacher=subject.teacher,
                    count=subject.pairs_per_week(curriculum.semester_weeks),
                )
            )
    return demands


def build_schedule(
    lessons: list[Lesson],
    college: str = "",
    week: str = "",
    dates: dict[str, str] | None = None,
) -> Schedule:
    """Собирает объект Schedule из списка занятий."""
    schedule = Schedule(college=college, week=week, dates=dates or {})
    for lesson in lessons:
        group = schedule.group(lesson.group)
        if group is None:
            group = Group(name=lesson.group)
            schedule.groups.append(group)
        group.lessons.append(lesson)
    return schedule


class WeekScheduler:
    """Генератор недельного расписания для набора требований."""

    def __init__(
        self,
        one_per_day: bool = True,
        days: list[str] | None = None,
        seed: int | None = None,
    ) -> None:
        """one_per_day — запрет ставить один предмет дважды в день;

        days — доступные дни недели (по умолчанию все шесть). Нужен
        для неполных недель семестра: 1-я неделя начинается со среды
        2 сентября, поэтому дней в ней только четыре — среда … суббота.

        seed — база случайности расстановки (обычно номер недели
        семестра): расстановка зависит от seed, поэтому у каждой
        недели получается своё расписание. seed=None — прежнее
        полностью детерминированное поведение (без случайности).
        """
        self.one_per_day = one_per_day
        if days is None:
            days = list(WEEKDAYS)
        allowed = set(days)
        self.days = [day for day in WEEKDAYS if day in allowed]
        if not self.days:
            raise ValueError("Список доступных дней недели пуст")
        self._rng = None if seed is None else random.Random(seed)

    # ── Публичный API ───────────────────────────────────────

    MAX_STEPS = 100_000  # бюджет перебора, защита от зависания

    def generate(self, demands: list[Demand]) -> list[Lesson]:
        """Возвращает список занятий на неделю либо ValueError.

        Заранее отсекаются заведомо невыполнимые требования —
        иначе backtracking ушёл бы в полный перебор.
        """
        units = self._expand(demands)
        if not units:
            return []

        days = len(self.days)
        per_subject: dict[tuple[str, str], int] = {}
        per_group: dict[str, int] = {}
        for u in units:
            per_subject[(u.group, u.subject)] = (
                per_subject.get((u.group, u.subject), 0) + 1
            )
            per_group[u.group] = per_group.get(u.group, 0) + 1
        if self.one_per_day:
            for (group, subject), count in per_subject.items():
                if count > days:
                    raise ValueError(
                        "Не удалось расставить требования: дисциплине "
                        f"«{subject}» нужно {count} пар, а дней в неделе всего "
                        f"{days} (ограничение: не более одного раза в день)"
                    )
        for group, count in per_group.items():
            if count > days * MAX_DAY_PAIRS:
                raise ValueError(
                    f"Не удалось расставить требования: группе «{group}» нужно "
                    f"{count} пар в неделю, а недельная вместимость — "
                    f"{days} дней × {MAX_DAY_PAIRS} пар = {days * MAX_DAY_PAIRS}"
                )

        caps = self._day_caps(per_group, per_subject)
        placed: list[tuple[Demand, str, int, str]] = []
        self._steps = 0
        if not self._place(units, 0, placed, caps):
            raise ValueError(
                "Не удалось расставить требования: "
                "слишком большая нагрузка при заданных ограничениях"
            )
        return [
            Lesson(
                day=d,
                group=u.group,
                number=n,
                subject=u.subject,
                room=r,
                teacher=u.teacher,
            )
            for u, d, n, r in placed
        ]

    @staticmethod
    def from_group_lessons(lessons: list[Lesson]) -> list[Demand]:
        """Строит требования из фактических занятий группы за неделю.

        Используется для пересборки недели группы: нагрузка
        (дисциплина → число пар) сохраняется, расстановка — новая.
        Кабинеты дисциплины собираются в список предпочтения,
        преподаватель берётся из занятий.
        """
        counter: dict[tuple[str, str], list[Lesson]] = {}
        for l in lessons:
            key = (l.group, l.subject)
            counter.setdefault(key, []).append(l)
        demands: list[Demand] = []
        for (group, subject), items in counter.items():
            rooms: list[str] = []
            for i in items:
                if i.room and i.room not in rooms:
                    rooms.append(i.room)
            teacher = next((i.teacher_label for i in items if i.teacher_label), "")
            demands.append(
                Demand(
                    group=group,
                    subject=subject,
                    rooms=rooms,
                    teacher=teacher,
                    count=len(items),
                )
            )
        return demands

    # ── Внутреннее ──────────────────────────────────────────

    def _expand(self, demands: list[Demand]) -> list[Demand]:
        """Разворачивает требования в юниты, жадная сортировка.

        «Тяжёлые» дисциплины (много пар) идут первыми; при заданном
        seed дисциплины одного объёма перемешиваются — порядок
        расстановки зависит от недели.
        """
        units: list[Demand] = []
        for d in demands:
            for _ in range(max(1, d.count)):
                units.append(d)
        if self._rng is None:
            # тяжёлые дисциплины (много пар) — первыми
            return sorted(units, key=lambda u: (-u.count, u.subject, u.group))
        return sorted(units, key=lambda u: (-u.count, self._rng.random()))

    def _day_caps(
        self,
        per_group: dict[str, int],
        per_subject: dict[tuple[str, str], int],
    ) -> dict[str, dict[str, int]]:
        """Дневные лимиты пар для каждой группы.

        Пары концентрируются в нескольких днях: сначала дни
        заполняются до MAX_DAY_PAIRS (4) пар, остаток даёт дни по 3 —
        так неделя выглядит как «4 + 3 + 3 + 3», а не «по 2 каждый
        день». Число занятых дней не меньше числа пар самой объёмной
        дисциплины (иначе «один предмет раз в день» не выполнить).
        Без seed пары концентрируются в первых днях недели, при
        заданном seed набор «загруженных» дней выбирается случайно —
        у каждой недели свои свободные дни.
        """
        caps: dict[str, dict[str, int]] = {}
        day_order = list(self.days)
        if self._rng is not None:
            self._rng.shuffle(day_order)
        for group, total in per_group.items():
            biggest = 1
            if self.one_per_day:
                biggest = max(
                    (
                        count
                        for (g, _subject), count in per_subject.items()
                        if g == group
                    ),
                    default=1,
                )
            used = min(
                max(
                    (total + MAX_DAY_PAIRS - 1) // MAX_DAY_PAIRS,  # ⌈total/4⌉
                    biggest,
                ),
                len(self.days),
            )
            base, extra = divmod(total, used)
            caps[group] = {
                day: base + (1 if i < extra else 0)
                for i, day in enumerate(day_order[:used])
            }
        return caps

    def _day_loads(self, group: str, placed) -> dict[str, int]:
        """Число уже поставленных пар группы по дням недели."""
        loads = {day: 0 for day in self.days}
        for u, d, n, r in placed:
            if u.group == group:
                loads[d] = loads.get(d, 0) + 1
        return loads

    def _candidates(
        self,
        group: str,
        placed,
        caps: dict[str, dict[str, int]] | None = None,
    ) -> list[tuple[str, int]]:
        """Слоты-кандидаты для группы: наименее загруженные дни первыми.

        Порядок: (нагрузка дня, номер пары, день недели) — но только
        по дням с ненулевым дневным лимитом. Концентрацию пар в
        3–4 в день обеспечивает лимит из _day_caps (первые дни
        недели), а внутри этих дней пары распределяются равномерно —
        дисциплины не сбиваются в один день. Номер пары ограничен
        сеткой звонков дня (пн — 6, вт–пт — 7, сб — 4 пары), поэтому
        в субботу пары выше 4-й не появляются в принципе. Если слот
        занят (кабинет или сама группа), пара уходит на следующий
        номер — вплоть до последней пары дня.
        """
        loads = self._day_loads(group, placed)
        day_cap = (caps or {}).get(group, {})
        positions = [
            (day, number)
            for day in self.days
            if day_cap.get(day, 0) > 0
            for number in range(1, day_pair_count(day) + 1)
        ]
        if self._rng is not None:
            # случайный порядок слотов: при равной загрузке дней пары
            # попадают на разные номера и разные дни (зависит от seed)
            self._rng.shuffle(positions)
            return sorted(positions, key=lambda p: (loads[p[0]], p[1]))
        return sorted(
            positions,
            key=lambda p: (loads[p[0]], p[1], self.days.index(p[0])),
        )

    def _place(
        self,
        units: list[Demand],
        idx: int,
        placed: list[tuple[Demand, str, int, str]],
        caps: dict[str, dict[str, int]],
    ) -> bool:
        """Рекурсивный backtracking: расставить units[idx:]."""
        self._steps += 1
        if self._steps > self.MAX_STEPS:
            raise ValueError(
                "Не удалось расставить требования: "
                "превышен лимит перебора ("
                f"{self.MAX_STEPS} шагов)"
            )
        if idx == len(units):
            return True
        unit = units[idx]
        for day, number in self._candidates(unit.group, placed, caps):
            if not self._fits(unit, day, number, placed, caps):
                continue
            room = self._free_room(unit, day, number, placed)
            if room is None:
                continue
            placed.append((unit, day, number, room))
            if self._place(units, idx + 1, placed, caps):
                return True
            placed.pop()
        return False

    def _fits(
        self,
        unit: Demand,
        day: str,
        number: int,
        placed,
        caps: dict[str, dict[str, int]],
    ) -> bool:
        """Проверяет ограничения группы для слота (day, number)."""
        if not 1 <= number <= day_pair_count(day):
            return False  # вне сетки звонков дня (в субботу — 4 пары)
        limit = caps.get(unit.group, {}).get(day, 0)
        day_pairs = 0
        occupied: list[int] = []
        for u, d, n, r in placed:
            if u.group != unit.group or d != day:
                continue
            day_pairs += 1
            occupied.append(n)
            if n == number:
                return False  # слот у группы уже занят
            if self.one_per_day and u.subject == unit.subject:
                return False  # дисциплина уже стоит в этот день
        if day_pairs >= limit:
            return False  # дневной лимит группы (3–4 пары)
        if occupied and number not in (min(occupied) - 1, max(occupied) + 1):
            return False  # «окно»: пара не примыкает к блоку пар группы
        return True

    def _free_room(self, unit: Demand, day: str, number: int, placed) -> str | None:
        """Первый свободный кабинет дисциплины в слоте (day, number).

        Возвращает None, если все кабинеты из списка заняты другими
        группами. Если список кабинетов пуст — кабинет не назначается.
        При заданном seed порядок предпочтения кабинетов перемешивается
        (детерминированно для конкретной недели).
        """
        if not unit.rooms:
            return ""
        rooms = list(unit.rooms)
        if self._rng is not None:
            self._rng.shuffle(rooms)
        busy = {(d, n, r) for u, d, n, r in placed if r}
        for room in rooms:
            if (day, number, room) not in busy:
                return room
        return None


def format_generated_week(lessons: list[Lesson], college: str = "") -> str:
    """Текстовый вывод автогенерированного расписания по дням."""
    w = 64
    lines = [
        "Автогенерация расписания (жадный + backtracking)",
        college,
        "=" * w,
    ]
    by_day: dict[str, list[Lesson]] = {}
    for l in lessons:
        by_day.setdefault(l.day, []).append(l)
    for day in WEEKDAYS:
        items = sorted(by_day.get(day, []), key=lambda l: l.number)
        if not items:
            continue
        lines.append("")
        lines.append(day.upper())
        lines.append("-" * w)
        for l in items:
            slot = time_slot(l.number, l.day)
            time = slot.time if slot else "—"
            room = f" — каб. {l.room}" if l.room else ""
            teacher = f" — преп. {l.teacher_label}" if l.teacher_label else ""
            lines.append(
                f"  {l.number}-я пара {time}  {display_name(l.subject)}{room}{teacher}"
            )
        lines.append("-" * w)
    lines.append("=" * w)
    lines.append(
        f"У группы — не более {MAX_DAY_PAIRS} пар в день, без «окон» между "
        f"парами; сетка звонков: пн — 6 пар, вт–пт — 7, сб — 4. "
        f"Перемены между парами (вт–пт): "
        + ", ".join(f"{break_after(s.number)} мин" for s in BELL_SCHEDULE[:-1])
        + "."
    )
    return "\n".join(lines)
