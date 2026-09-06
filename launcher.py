"""
launcher.py — RoasterInterface güncelleme başlatıcısı (iskelet).

Bu ayrı bir PyInstaller hedefi olarak derlenir (launcher.spec).
Masaüstü kısayolu artık main.exe yerine bunu çalıştırır.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

APP_DIR = Path(__file__).parent / "app"          # ana uygulamanın kurulu olduğu klasör
VERSION_FILE = APP_DIR / "version.txt"
BACKUP_DIR = Path(__file__).parent / "app_backup"
MANIFEST_URL = "https://ORNEK-SUNUCUNUZ/roasterinterface/version.json"
TEMP_ZIP = Path(__file__).parent / "_update.zip"


def get_local_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return "0.0.0"


def fetch_remote_manifest() -> dict | None:
    try:
        resp = requests.get(MANIFEST_URL, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[launcher] Manifest alınamadı, mevcut sürümle devam: {e}")
        return None


def is_update_needed(local: str, remote: str) -> bool:
    # Basit karşılaştırma; gerekirse 'packaging.version' kullanılabilir
    return tuple(map(int, remote.split("."))) > tuple(map(int, local.split(".")))


def download_update(url: str) -> Path:
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(TEMP_ZIP, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    return TEMP_ZIP


def verify_checksum(file_path: Path, expected_sha256: str) -> bool:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected_sha256.lower()


def backup_current_app():
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    shutil.copytree(APP_DIR, BACKUP_DIR)


def apply_update(zip_path: Path):
    backup_current_app()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(APP_DIR)
    zip_path.unlink(missing_ok=True)


def rollback():
    if BACKUP_DIR.exists():
        if APP_DIR.exists():
            shutil.rmtree(APP_DIR)
        shutil.move(str(BACKUP_DIR), str(APP_DIR))
        print("[launcher] Güncelleme başarısız, önceki sürüme dönüldü.")


def launch_main_app():
    main_exe = APP_DIR / "main.exe"
    subprocess.Popen([str(main_exe)])


def main():
    local_version = get_local_version()
    manifest = fetch_remote_manifest()

    if manifest and is_update_needed(local_version, manifest["version"]):
        try:
            print(f"[launcher] Yeni sürüm bulundu: {manifest['version']}")
            zip_path = download_update(manifest["url"])
            if not verify_checksum(zip_path, manifest["sha256"]):
                raise ValueError("Checksum uyuşmuyor, indirilen dosya güvenilmez.")
            apply_update(zip_path)
            VERSION_FILE.write_text(manifest["version"])
        except Exception as e:
            print(f"[launcher] Güncelleme başarısız: {e}")
            rollback()

    try:
        launch_main_app()
    except Exception as e:
        print(f"[launcher] Ana uygulama başlatılamadı: {e}")
        rollback()
        launch_main_app()  # yedekle tekrar dene

    sys.exit(0)


if __name__ == "__main__":
    main()