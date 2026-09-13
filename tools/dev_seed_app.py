"""
dev_seed_app.py — `app/` klasörünü "zaten kurulu bir sürüm" gibi başlangıç
durumuna getirir (geliştirme/test amaçlı).

Gerçek hayatta `app/` klasörünü bir kurulum programı (installer) doldurur.
Biz henüz kurulum programı yazmadık, bu yüzden launcher'ın "indirilen
güncellemeyi gerçekten uygulayıp çalıştırdığını" test edebilmek için
elle bir başlangıç noktası lazım — bu araç onu sağlıyor.

Kullanım:
    python tools/dev_seed_app.py

`app/` klasörü zaten varsa hiçbir şey yapmaz (üzerine yazmaz) — yeniden
baştan başlamak istersen klasörü elle sil ve tekrar çalıştır.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.dev_app_builder import build_runtime_zip  # noqa: E402

INITIAL_VERSION = "1.0.0"


def seed(app_dir: Path) -> None:
    if app_dir.exists():
        print(f"[dev_seed_app] '{app_dir}' zaten var, dokunmadım. "
              f"Baştan başlamak istersen klasörü sil ve tekrar çalıştır.")
        return

    app_dir.mkdir(parents=True)

    zip_path = app_dir.parent / "_seed_build.zip"
    build_runtime_zip(PROJECT_ROOT, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(app_dir)
    zip_path.unlink()

    (app_dir / "version.txt").write_text(INITIAL_VERSION)

    print(f"[dev_seed_app] '{app_dir}' oluşturuldu, sürüm: {INITIAL_VERSION}")
    print(f"[dev_seed_app] İçinde: {sorted(p.name for p in app_dir.iterdir())}")


if __name__ == "__main__":
    seed(PROJECT_ROOT / "app")
