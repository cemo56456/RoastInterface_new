"""
test_dev_app_builder.py — dev_app_builder.build_runtime_zip testleri.

Gerçek proje kökü üzerinde (bu depo) gerçek bir zip üretip içeriğini
doğruluyor — mock yok.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from tools.dev_app_builder import build_runtime_zip

PROJECT_ROOT = Path(__file__).parent.parent


def test_build_runtime_zip_includes_main_py(tmp_path):
    output = build_runtime_zip(PROJECT_ROOT, tmp_path / "out.zip")

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()

    assert "main.py" in names


def test_build_runtime_zip_includes_runtime_packages(tmp_path):
    output = build_runtime_zip(PROJECT_ROOT, tmp_path / "out.zip")

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()

    assert any(n.startswith("services/") and n.endswith(".py") for n in names)
    assert any(n.startswith("screens/") and n.endswith(".py") for n in names)
    assert any(n.startswith("config/") and n.endswith(".py") for n in names)


def test_build_runtime_zip_excludes_dev_only_dirs(tmp_path):
    output = build_runtime_zip(PROJECT_ROOT, tmp_path / "out.zip")

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()

    assert not any(n.startswith("tests/") for n in names)
    assert not any(n.startswith("tools/") for n in names)
    assert not any(".venv" in n for n in names)


def test_build_runtime_zip_content_matches_source(tmp_path):
    output = build_runtime_zip(PROJECT_ROOT, tmp_path / "out.zip")

    with zipfile.ZipFile(output) as zf:
        zipped_main = zf.read("main.py").decode("utf-8")

    real_main = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert zipped_main == real_main
