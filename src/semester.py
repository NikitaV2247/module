# -*- coding: utf-8 -*-
"""Семестровый период и учебные недели (2 сентября – 20 декабря 2026 г.).

Модуль отвечает на вопросы «какая это неделя семестра» и «какие
дни и даты у неё есть». Расписание можно собрать на любую неделю
периода — например, на 1-ю неделю сентября или на 4-ю неделю
ноября (23–29 ноября), — либо на один день по дате (8 октября).

    semester = Semester(date(2026, 9, 2), date(2026, 12, 20))
    semester.weeks                                # 16 недель
    semester.week_for_date(date(2026, 11, 23))    # 13-я неделя
    semester.resolve("13")                        # по номеру
    semester.resolve("2026-11-23")                # по дате недели
    semester.day_for_date(date(2026, 10, 8))      # (6-я неделя, «Четверг»)

Недели нумеруются с 1 и начинаются с понедельника. В неделю входят
учебные дни (понедельник … суббота), попадающие в период семестра:
первая неделя начинается в среду 2 сентября, поэтому в ней только
четыре дня — среда, четверг, пятница и суббота.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.models import WEEKDAYS

# Родительный падеж месяцев для подписей «2–6 сентября 2026 г.»
MONTHS_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

# Поддерживаемые форматы дат в аргументах командной строки
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y")


def parse_date(value: str) -> date:
    """«2026-11-23» или «23.11.2026» → date.

    ValueError — если строка не похожа на дату.
    """
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Не удалось разобрать дату «{value}»: "
        "ожидается ГГГГ-ММ-ДД (2026-11-23) или ДД.ММ.ГГГГ (23.11.2026)"
    )


def _day_label(d: date) -> str:
    """«8 октября» — день месяца с месяцем в родительном падеже."""
    return f"{d.day} {MONTHS_GENITIVE[d.month]}"


def _week_label(first: date, last: date) -> str:
    """Подпись диапазона дней недели: «2–6 сентября 2026 г.».

    Если неделя переходит на следующий месяц — «28 сентября –
    3 октября 2026 г.».
    """
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day}–{last.day} {MONTHS_GENITIVE[last.month]} {last.year} г."
    if first.year == last.year:
        return f"{_day_label(first)} – {_day_label(last)} {last.year} г."
    return f"{_day_label(first)} {first.year} г. – {_day_label(last)} {last.year} г."


@dataclass(frozen=True)
class SemesterWeek:
    """Учебная неделя семестра.

    Атрибуты:
        number:    номер недели семестра (1–16);
        monday:    календарный понедельник недели;
        days:      учебные дни недели внутри периода семестра
                   (для 1-й недели — среда … суббота);
        day_dates: календарная дата каждого учебного дня;
        label:     подпись недели — «2–6 сентября 2026 г.».
    """

    number: int
    monday: date
    days: tuple[str, ...]
    day_dates: dict[str, date]
    label: str

    @property
    def dates(self) -> dict[str, str]:
        """Дни недели с датами в формате данных: «Среда» → «02.09»."""
        return {day: d.strftime("%d.%m") for day, d in self.day_dates.items()}


class Semester:
    """Период семестра: список учебных недель и выбор по дате."""

    def __init__(self, start: date, end: date) -> None:
        if start > end:
            raise ValueError(
                f"Начало семестра ({start:%d.%m.%Y}) позже конца ({end:%d.%m.%Y})"
            )
        self.start = start
        self.end = end
        self._weeks: list[SemesterWeek] | None = None

    # ── Недели периода ───────────────────────────────────────

    @property
    def weeks(self) -> list[SemesterWeek]:
        """Учебные недели периода, начиная с понедельника 1-й недели."""
        if self._weeks is None:
            result: list[SemesterWeek] = []
            monday = self.start - timedelta(days=self.start.weekday())
            while monday <= self.end:
                day_dates = {
                    WEEKDAYS[offset]: monday + timedelta(days=offset)
                    for offset in range(len(WEEKDAYS))
                    if self.start <= monday + timedelta(days=offset) <= self.end
                }
                if day_dates:  # неделя без учебных дней не нумеруется
                    ordered = [day_dates[day] for day in WEEKDAYS if day in day_dates]
                    result.append(
                        SemesterWeek(
                            number=len(result) + 1,
                            monday=monday,
                            days=tuple(WEEKDAYS[d.weekday()] for d in ordered),
                            day_dates=day_dates,
                            label=_week_label(ordered[0], ordered[-1]),
                        )
                    )
                monday += timedelta(weeks=1)
            self._weeks = result
        return self._weeks

    def week_by_number(self, number: int) -> SemesterWeek:
        """Неделя по номеру семестра (1–16)."""
        weeks = self.weeks
        if not 1 <= number <= len(weeks):
            raise ValueError(
                f"В семестре {len(weeks)} недель (1–{len(weeks)}), "
                f"запрошена неделя {number}"
            )
        return weeks[number - 1]

    def week_for_date(self, value: date) -> SemesterWeek:
        """Неделя, в которую попадает дата (дата внутри периода)."""
        if not self.start <= value <= self.end:
            raise ValueError(
                f"Дата {value:%d.%m.%Y} вне периода семестра "
                f"({self.start:%d.%m.%Y} – {self.end:%d.%m.%Y})"
            )
        monday = value - timedelta(days=value.weekday())
        for week in self.weeks:
            if week.monday == monday:
                return week
        raise ValueError(  # защита на случай воскресенья вне учебных дней
            f"Для даты {value:%d.%m.%Y} не нашлось учебной недели"
        )

    def resolve(self, spec: str) -> SemesterWeek:
        """Неделя по строке: номер («13») или дата («2026-11-23»)."""
        text = spec.strip()
        if text.isdigit():
            return self.week_by_number(int(text))
        return self.week_for_date(parse_date(text))

    # ── Один день ────────────────────────────────────────────

    def day_for_date(self, value: date) -> tuple[SemesterWeek, str]:
        """Дата → (неделя семестра, название дня недели).

        Воскресенье — выходной: ValueError.
        """
        if value.weekday() >= len(WEEKDAYS):
            raise ValueError(f"{value:%d.%m.%Y} — воскресенье, выходной день")
        week = self.week_for_date(value)
        day = WEEKDAYS[value.weekday()]
        if day not in week.days:
            raise ValueError(f"День {value:%d.%m.%Y} не входит в учебные дни недели")
        return week, day

    # ── Подписи ──────────────────────────────────────────────

    def week_title(self, week: SemesterWeek) -> str:
        """«23–29 ноября 2026 г. · 13-я неделя семестра»."""
        return f"{week.label} · {week.number}-я неделя семестра"

    def day_title(self, week: SemesterWeek, day: str) -> str:
        """«Четверг, 8 октября 2026 г.» — подпись одного дня."""
        d = week.day_dates[day]
        return f"{day}, {d.day} {MONTHS_GENITIVE[d.month]} {d.year} г."
