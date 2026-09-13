"""
launcher.py — RoasterInterface güncelleme mantığı (`Launcher` sınıfı).

Bilinçli olarak `kivy` import ETMEZ — saf mantık burada, görsel arayüz
`launcher_app.py`'de. Masaüstü kısayolu (ve PyInstaller hedefi) asıl
olarak `launcher_app.py`'yi çalıştıracak; bu dosyanın `__main__` bloğu
sadece GUI'siz/headless bir yedek (debug, CI gibi görüntü olmayan
ortamlar için).

Diğer servislerle (`ModbusTCPClient`, `ProfileStore`) aynı kalıp: tek bir
sınıf, config `__init__`'te, I/O metotları `(sonuç, hata)` tuple'ı döner.
Bu sayede gerçek bir güncelleme sunucusu olmadan da (bkz.
`tools/update_server_simulator.py`) uçtan uca test edilebiliyor —
`app_dir`/`manifest_url` dışarıdan verildiği için testler bunları geçici
dizinlere ve yerel sahte sunucuya yönlendirebiliyor.

**`LAUNCHER_MANIFEST_URL` şu an YER TUTUCUDUR** (bkz. config/settings.py)
— kullanıcının henüz gerçek bir güncelleme sunucusu yok.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable

import requests


class Launcher:
    def __init__(
        self,
        app_dir: str | Path,
        manifest_url: str,
        backup_dir: str | Path | None = None,
        temp_zip: str | Path | None = None,
        timeout: float = 5.0,
        dev_main_script: str | Path | None = None,
    ):
        self.app_dir = Path(app_dir)
        self.version_file = self.app_dir / "version.txt"
        self.manifest_url = manifest_url
        self.backup_dir = Path(backup_dir) if backup_dir else self.app_dir.parent / "app_backup"
        self.temp_zip = Path(temp_zip) if temp_zip else self.app_dir.parent / "_update.zip"
        self.timeout = timeout

        # GEÇİCİ (bkz. launch_main_app): main.py henüz PyInstaller ile
        # main.exe'ye paketlenmedi. dev_main_script verilirse, launcher
        # gerçek bir .exe aramak yerine bu Python dosyasını `python ...`
        # ile çalıştırır. PyInstaller paketlemesi yapıldığında bu
        # parametre (ve launch_main_app'teki dallanma) tamamen
        # kaldırılmalı — üretimde her zaman gerçek main.exe kullanılacak.
        self.dev_main_script = Path(dev_main_script) if dev_main_script else None

    # ------------------------------------------------------------------ #
    # Sürüm bilgisi
    # ------------------------------------------------------------------ #

    def get_local_version(self) -> str:
        if self.version_file.exists():
            return self.version_file.read_text().strip()
        return "0.0.0"

    @staticmethod
    def is_update_needed(local: str, remote: str) -> bool:
        return tuple(map(int, remote.split("."))) > tuple(map(int, local.split(".")))

    # ------------------------------------------------------------------ #
    # Ağ işlemleri
    # ------------------------------------------------------------------ #

    def fetch_remote_manifest(self) -> tuple[dict | None, str | None]:
        try:
            resp = requests.get(self.manifest_url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json(), None
        except Exception as e:
            return None, f"Manifest alınamadı: {e}"

    def download_update(
        self, url: str, on_progress: Callable[[int, int], None] | None = None
    ) -> tuple[Path | None, str | None]:
        """`on_progress(indirilen_bayt, toplam_bayt)` her chunk'ta çağrılır.

        `toplam_bayt`, sunucu `Content-Length` göndermezse `0` olur —
        çağıran taraf bunu "belirsiz ilerleme" olarak yorumlamalı.
        """
        try:
            with requests.get(url, stream=True, timeout=self.timeout * 6) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                with open(self.temp_zip, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress is not None:
                            on_progress(downloaded, total)
        except Exception as e:
            return None, f"İndirme başarısız: {e}"

        return self.temp_zip, None

    # ------------------------------------------------------------------ #
    # Doğrulama ve uygulama
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_checksum(file_path: str | Path, expected_sha256: str) -> bool:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest().lower() == expected_sha256.lower()

    def backup_current_app(self) -> None:
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
        if self.app_dir.exists():
            shutil.copytree(self.app_dir, self.backup_dir)

    def apply_update(self, zip_path: str | Path) -> tuple[bool, str | None]:
        zip_path = Path(zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # zip-slip koruması: her girişin çözümlenmiş yolu app_dir
                # dışına çıkarsa (ör. "../../evil.txt") hiçbir şey açmadan
                # reddet. `extractall()` bunu kendisi kontrol etmiyor.
                app_dir_resolved = self.app_dir.resolve()
                for member in zf.namelist():
                    target = (self.app_dir / member).resolve()
                    if not (target == app_dir_resolved or app_dir_resolved in target.parents):
                        return False, f"Güvensiz zip girişi (zip-slip): {member!r}"

                self.backup_current_app()
                zf.extractall(self.app_dir)
        except (OSError, zipfile.BadZipFile) as e:
            return False, f"Güncelleme uygulanamadı: {e}"

        zip_path.unlink(missing_ok=True)
        return True, None

    def rollback(self) -> tuple[bool, str | None]:
        if not self.backup_dir.exists():
            return False, "Yedek bulunamadı, geri dönülemedi"

        try:
            if self.app_dir.exists():
                shutil.rmtree(self.app_dir)
            shutil.move(str(self.backup_dir), str(self.app_dir))
        except OSError as e:
            return False, f"Geri dönüş başarısız: {e}"

        return True, None

    # ------------------------------------------------------------------ #
    # Ana uygulamayı başlatma
    # ------------------------------------------------------------------ #

    def launch_main_app(self) -> subprocess.Popen:
        if self.dev_main_script is not None:
            # GEÇİCİ geliştirme yolu — bkz. __init__'teki not.
            return subprocess.Popen([sys.executable, str(self.dev_main_script)])

        main_exe = self.app_dir / "main.exe"
        return subprocess.Popen([str(main_exe)])

    # ------------------------------------------------------------------ #
    # Orkestrasyon
    # ------------------------------------------------------------------ #

    def run(
        self,
        on_status: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> bool:
        """Sürüm kontrolü + güncelleme + başlatma akışının tamamı.

        `on_status(mesaj)` her aşama geçişinde çağrılır (bir GUI'nin
        "Sürüm kontrol ediliyor...", "İndiriliyor...", "Başlatılıyor..."
        gibi durum metnini güncellemesi için). `on_progress(indirilen,
        toplam)` sadece indirme sırasında çağrılır — bkz.
        `download_update`.

        Ana uygulama hiç başlatılamazsa (yedekten sonra bile) `False`,
        aksi halde `True` döner. Hiçbir zaman exception fırlatmaz —
        `sys.exit()` de çağırmaz, çağıran taraf (`__main__` bloğu veya
        bir GUI) sonucu görüp karar verir. Bu, testlerin `run()`'ı
        doğrudan çağırabilmesi için bilinçli bir tasarım (aksi halde her
        test süreci sonlandırırdı).
        """

        def status(msg: str) -> None:
            print(f"[launcher] {msg}")
            if on_status is not None:
                on_status(msg)

        status("Sürüm kontrol ediliyor...")
        local_version = self.get_local_version()
        manifest, err = self.fetch_remote_manifest()

        if manifest is not None and err is None and self.is_update_needed(local_version, manifest["version"]):
            status(f"Yeni sürüm bulundu: {manifest['version']}")
            update_ok = self._download_and_apply(manifest, on_status=status, on_progress=on_progress)
            if not update_ok:
                self.rollback()
        elif err is not None:
            status("Sürüm kontrolü atlandı (güncelleme sunucusuna ulaşılamadı)")
        else:
            status("Güncel sürümdesiniz")

        status("Başlatılıyor...")
        try:
            self.launch_main_app()
        except OSError as e:
            status(f"Ana uygulama başlatılamadı: {e}")
            self.rollback()
            try:
                self.launch_main_app()  # yedekle tekrar dene
            except OSError as e2:
                status(f"Ana uygulama yedekten de başlatılamadı: {e2}")
                return False

        return True

    def _download_and_apply(
        self,
        manifest: dict,
        on_status: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> bool:
        def status(msg: str) -> None:
            print(f"[launcher] {msg}")
            if on_status is not None:
                on_status(msg)

        status("Güncelleme indiriliyor...")
        zip_path, err = self.download_update(manifest["url"], on_progress=on_progress)
        if err is not None:
            status(f"Güncelleme başarısız: {err}")
            return False

        status("Checksum doğrulanıyor...")
        if not self.verify_checksum(zip_path, manifest["sha256"]):
            status("Güncelleme başarısız: checksum uyuşmuyor, indirilen dosya güvenilmez.")
            return False

        status("Güncelleme uygulanıyor...")
        ok, err = self.apply_update(zip_path)
        if not ok:
            status(f"Güncelleme başarısız: {err}")
            return False

        self.version_file.write_text(manifest["version"])
        return True


if __name__ == "__main__":
    # Headless yedek — asıl GUI girişi launcher_app.py. Görüntü sunucusu
    # olmayan bir ortamda (CI, elle debug) hâlâ konsoldan çalıştırılabilsin
    # diye burada bırakıldı.
    from config import settings

    dev_main_script = None
    if settings.LAUNCHER_DEV_MAIN_SCRIPT:
        dev_main_script = Path(__file__).parent / settings.LAUNCHER_DEV_MAIN_SCRIPT

    launcher = Launcher(
        app_dir=Path(__file__).parent / settings.LAUNCHER_APP_DIR,
        manifest_url=settings.LAUNCHER_MANIFEST_URL,
        timeout=settings.LAUNCHER_TIMEOUT,
        dev_main_script=dev_main_script,
    )
    ok = launcher.run()
    sys.exit(0 if ok else 1)
