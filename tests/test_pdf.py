# -*- coding: utf-8 -*-
"""Тесты экспорта недели в PDF (src/pdf_export.py)."""

import os
import shutil

import pytest

from src.generator import ScheduleGenerator
from src.loader import DataLoader
from src.pdf_export import _styles, save_week_pdf


@pytest.fixture(scope="module")
def app():
    schedule = DataLoader("data/schedule.json").load()
    gen = ScheduleGenerator(schedule)
    week = gen.group_week("4-1П9")
    return schedule, gen, week


def test_save_week_pdf_file(app, tmp_path):
    schedule, _gen, week = app
    path = tmp_path / "week.pdf"
    save_week_pdf(
        "4-1П9",
        week,
        str(path),
        college=schedule.college,
        week=schedule.week,
        dates=schedule.dates,
    )
    assert path.exists()
    head = path.read_bytes()[:8]
    assert head.startswith(b"%PDF")
    assert os.path.getsize(path) > 10_000


def test_pdf_registers_fonts_and_columns(app):
    """Шрифты DejaVu регистрируются; стиль таблицы доступен."""
    schedule, _gen, week = app
    styles = _styles()
    assert styles is not None
    assert "header" in styles and "cell" in styles


# ── v0.7.2: без нижней легенды, с преподавателем ────────────


def test_pdf_legend_style_removed(app):
    """Стиль легенды и функция _breaks_legend удалены из модуля."""
    import src.pdf_export as pdf_export

    styles = _styles()
    assert "legend" not in styles
    assert not hasattr(pdf_export, "_breaks_legend")


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="нет pdftotext")
def test_pdf_no_footer_and_teacher_shown(app, tmp_path):
    """Внизу PDF нет строки-легенды, в ячейках виден преподаватель."""
    import subprocess

    schedule, _gen, week = app
    path = tmp_path / "week.pdf"
    save_week_pdf(
        "4-1П9",
        week,
        str(path),
        college=schedule.college,
        week=schedule.week,
        dates=schedule.dates,
    )
    text = subprocess.run(
        ["pdftotext", str(path), "-"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    assert "Пустая ячейка" not in text  # легенда убрана из PDF
    assert "перемены между парами" not in text.lower()
    assert "преп. Смирнов А. В." in text  # преподаватель в ячейке
    assert "преп. Лебедева Т. Н." in text
