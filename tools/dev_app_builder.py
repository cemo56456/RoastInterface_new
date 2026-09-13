"""
dev_app_builder.py — Geliştirme sırasında "yeni bir sürüm yayınlamayı"
simüle etmek için, projenin çalışma zamanı dosyalarını (main.py +
config/screens/services/widgets) bir zip'e paketler.

**Bu, gerçek PyInstaller paketlemesinin YERİNİ TUTMUYOR.** Sadece
launcher'ın "indir → app/ klasörüne uygula → başlat" akışını, gerçek bir
.exe olmadan uçtan uca test edebilmek için bir geliştirme aracı — bkz.
tools/dev_seed_app.py ve tools/dev_release_update.py.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

# main.py'nin çalışması için gereken, projenin "çalışma zamanı" kısmı.
# tests/, tools/, .venv/, handoff.md gibi geliştirme-zamanı şeyler hariç.
RUNTIME_FILES = ["main.py"]
RUNTIME_DIRS = ["config", "screens", "services", "widgets"]


def build_runtime_zip(project_root: str | Path, output_zip: str | Path) -> Path:
    """`project_root`'taki çalışma zamanı dosyalarını `output_zip`'e paketler."""
    project_root = Path(project_root)
    output_zip = Path(output_zip)

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in RUNTIME_FILES:
            src = project_root / name
            if src.exists():
                zf.write(src, arcname=name)

        for dirname in RUNTIME_DIRS:
            src_dir = project_root / dirname
            if not src_dir.is_dir():
                continue
            for path in src_dir.rglob("*.py"):
                zf.write(path, arcname=str(path.relative_to(project_root)))

    return output_zip
