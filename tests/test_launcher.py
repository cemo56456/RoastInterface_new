"""
test_launcher.py — Launcher testleri.

Gerçek bir güncelleme sunucusu yok (henüz kullanıcıda değil), bu yüzden
`tools/update_server_simulator.py` ile yerel bir sahte HTTP sunucusuna
karşı gerçek indirme/manifest testleri yapılıyor — sadece saf mantık
(sürüm karşılaştırma, checksum) değil, gerçek dosya/network akışı da
kapsanıyor. Tek mock edilen yer `launch_main_app` — gerçek bir `.exe`
bu makinede yok.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from launcher import Launcher
from tools.update_server_simulator import UpdateServerSimulator


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def app_dir(tmp_path) -> Path:
    d = tmp_path / "app"
    d.mkdir()
    (d / "version.txt").write_text("1.0.0")
    (d / "main.exe").write_text("ESKİ_SÜRÜM")
    return d


@pytest.fixture
def launcher(tmp_path, app_dir) -> Launcher:
    return Launcher(
        app_dir=app_dir,
        manifest_url="http://127.0.0.1:1/version.json",  # varsayılan olarak kullanılmıyor
        backup_dir=tmp_path / "app_backup",
        temp_zip=tmp_path / "_update.zip",
        timeout=2.0,
    )


@pytest.fixture
def update_server():
    sim = UpdateServerSimulator(host="127.0.0.1", port=0)
    sim.start()
    yield sim
    sim.stop()


# --------------------------------------------------------------------- #
# Saf mantık
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "local, remote, expected",
    [
        ("1.0.0", "1.0.1", True),
        ("1.0.0", "1.0.0", False),
        ("1.2.0", "1.1.9", False),
        ("1.9.0", "1.10.0", True),  # basamak sayısı farklı, string karşılaştırma değil
        ("0.0.0", "1.0.0", True),
    ],
)
def test_is_update_needed(local, remote, expected):
    assert Launcher.is_update_needed(local, remote) is expected


def test_get_local_version_missing_file(tmp_path):
    launcher = Launcher(app_dir=tmp_path / "yok", manifest_url="http://x")
    assert launcher.get_local_version() == "0.0.0"


def test_get_local_version_existing_file(launcher):
    assert launcher.get_local_version() == "1.0.0"


def test_verify_checksum_correct(tmp_path):
    file_path = tmp_path / "f.bin"
    file_path.write_bytes(b"merhaba dunya")
    assert Launcher.verify_checksum(file_path, _sha256_of(b"merhaba dunya")) is True


def test_verify_checksum_incorrect(tmp_path):
    file_path = tmp_path / "f.bin"
    file_path.write_bytes(b"merhaba dunya")
    assert Launcher.verify_checksum(file_path, "0" * 64) is False


# --------------------------------------------------------------------- #
# Ağ işlemleri — yerel sahte sunucuya karşı
# --------------------------------------------------------------------- #

def test_fetch_remote_manifest_success(launcher, update_server):
    update_server.set_manifest({"version": "1.1.0", "url": update_server.zip_url, "sha256": "abc"})
    launcher.manifest_url = update_server.manifest_url

    manifest, err = launcher.fetch_remote_manifest()

    assert err is None
    assert manifest == {"version": "1.1.0", "url": update_server.zip_url, "sha256": "abc"}


def test_fetch_remote_manifest_server_unreachable(launcher):
    launcher.manifest_url = "http://127.0.0.1:1/version.json"  # kapalı port

    manifest, err = launcher.fetch_remote_manifest()

    assert manifest is None
    assert err is not None


def test_download_update_real_bytes(launcher, update_server):
    payload = _make_zip_bytes({"main.exe": b"YENI_SURUM"})
    update_server.set_zip_bytes(payload)

    path, err = launcher.download_update(update_server.zip_url)

    assert err is None
    assert path.read_bytes() == payload


# --------------------------------------------------------------------- #
# apply_update / zip-slip koruması
# --------------------------------------------------------------------- #

def test_apply_update_extracts_real_files(launcher, tmp_path):
    zip_path = tmp_path / "update.zip"
    zip_path.write_bytes(_make_zip_bytes({"main.exe": b"YENI_SURUM"}))

    ok, err = launcher.apply_update(zip_path)

    assert ok is True
    assert err is None
    assert (launcher.app_dir / "main.exe").read_bytes() == b"YENI_SURUM"
    assert not zip_path.exists()  # işlem sonunda temizleniyor


def test_apply_update_creates_backup_before_extracting(launcher, tmp_path):
    zip_path = tmp_path / "update.zip"
    zip_path.write_bytes(_make_zip_bytes({"main.exe": b"YENI_SURUM"}))

    launcher.apply_update(zip_path)

    assert (launcher.backup_dir / "main.exe").read_text() == "ESKİ_SÜRÜM"


def test_apply_update_rejects_zip_slip(launcher, tmp_path):
    zip_path = tmp_path / "kotu.zip"
    zip_path.write_bytes(_make_zip_bytes({"../evil.txt": b"kotu icerik"}))

    ok, err = launcher.apply_update(zip_path)

    assert ok is False
    assert "zip-slip" in err.lower() or "güvensiz" in err.lower()
    # app_dir'in dışına hiçbir şey yazılmamalı
    assert not (launcher.app_dir.parent / "evil.txt").exists()


# --------------------------------------------------------------------- #
# rollback
# --------------------------------------------------------------------- #

def test_rollback_restores_previous_content(launcher):
    launcher.backup_current_app()

    # Uygulama klasörünü "bozalım" (başarısız güncelleme simülasyonu)
    (launcher.app_dir / "main.exe").write_text("BOZUK")

    ok, err = launcher.rollback()

    assert ok is True
    assert err is None
    assert (launcher.app_dir / "main.exe").read_text() == "ESKİ_SÜRÜM"


def test_rollback_fails_gracefully_without_backup(launcher):
    ok, err = launcher.rollback()
    assert ok is False
    assert err is not None


# --------------------------------------------------------------------- #
# launch_main_app — tek mock edilen yer (gerçek .exe yok)
# --------------------------------------------------------------------- #

def test_launch_main_app_calls_popen_with_correct_path(launcher, monkeypatch):
    mock_popen = MagicMock()
    monkeypatch.setattr("launcher.subprocess.Popen", mock_popen)

    launcher.launch_main_app()

    mock_popen.assert_called_once_with([str(launcher.app_dir / "main.exe")])


def test_run_does_not_crash_when_main_app_missing_both_attempts(launcher, update_server):
    """Regresyon testi: `app/main.exe` hiç yoksa (henüz paketlenmemiş bir
    geliştirme ortamı gibi) `run()` temiz bir hata mesajıyla `False`
    dönmeli, ikinci (yedekten sonraki) deneme de başarısız olunca
    çökmemeli."""
    update_server.set_manifest({"version": "1.0.0", "url": update_server.zip_url, "sha256": "x"})
    launcher.manifest_url = update_server.manifest_url

    # app_dir'de gerçekten main.exe yok (fixture sadece bir metin dosyası koyuyor,
    # gerçek çalıştırılabilir bir şey değil) -> launch_main_app() gerçekten OSError atar
    ok = launcher.run()  # exception fırlatmamalı

    assert ok is False


# --------------------------------------------------------------------- #
# run() — uçtan uca orkestrasyon
# --------------------------------------------------------------------- #

def test_run_updates_app_when_new_version_available(launcher, update_server, monkeypatch):
    monkeypatch.setattr(launcher, "launch_main_app", MagicMock())

    payload = _make_zip_bytes({"main.exe": b"YENI_SURUM"})
    update_server.set_zip_bytes(payload)
    update_server.set_manifest(
        {"version": "2.0.0", "url": update_server.zip_url, "sha256": _sha256_of(payload)}
    )
    launcher.manifest_url = update_server.manifest_url

    ok = launcher.run()

    assert ok is True
    assert launcher.get_local_version() == "2.0.0"
    assert (launcher.app_dir / "main.exe").read_bytes() == b"YENI_SURUM"
    launcher.launch_main_app.assert_called_once()


def test_run_skips_download_when_already_current(launcher, update_server, monkeypatch):
    monkeypatch.setattr(launcher, "launch_main_app", MagicMock())
    download_spy = MagicMock(wraps=launcher.download_update)
    monkeypatch.setattr(launcher, "download_update", download_spy)

    update_server.set_manifest({"version": "1.0.0", "url": update_server.zip_url, "sha256": "x"})
    launcher.manifest_url = update_server.manifest_url

    ok = launcher.run()

    assert ok is True
    download_spy.assert_not_called()
    assert launcher.get_local_version() == "1.0.0"


def test_run_rolls_back_on_checksum_mismatch(launcher, update_server, monkeypatch):
    monkeypatch.setattr(launcher, "launch_main_app", MagicMock())

    payload = _make_zip_bytes({"main.exe": b"YENI_SURUM"})
    update_server.set_zip_bytes(payload)
    update_server.set_manifest(
        {"version": "2.0.0", "url": update_server.zip_url, "sha256": "0" * 64}  # yanlış checksum
    )
    launcher.manifest_url = update_server.manifest_url

    ok = launcher.run()

    # Güncelleme reddedildi ama ana uygulama (mock) yine de başlatıldığı için True
    assert ok is True
    # Sürüm/asıl dosya güncellenmemiş olmalı (checksum reddetti)
    assert launcher.get_local_version() == "1.0.0"
    assert (launcher.app_dir / "main.exe").read_text() == "ESKİ_SÜRÜM"


# --------------------------------------------------------------------- #
# on_status / on_progress callback'leri
# --------------------------------------------------------------------- #

def test_run_calls_on_status_with_phase_messages(launcher, update_server, monkeypatch):
    monkeypatch.setattr(launcher, "launch_main_app", MagicMock())

    payload = _make_zip_bytes({"main.exe": b"YENI_SURUM"})
    update_server.set_zip_bytes(payload)
    update_server.set_manifest(
        {"version": "2.0.0", "url": update_server.zip_url, "sha256": _sha256_of(payload)}
    )
    launcher.manifest_url = update_server.manifest_url

    messages: list[str] = []
    launcher.run(on_status=messages.append)

    assert any("kontrol ediliyor" in m for m in messages)
    assert any("Yeni sürüm bulundu" in m for m in messages)
    assert any("indiriliyor" in m for m in messages)
    assert any("Başlatılıyor" in m for m in messages)


def test_run_calls_on_status_even_when_no_update_needed(launcher, update_server, monkeypatch):
    monkeypatch.setattr(launcher, "launch_main_app", MagicMock())
    update_server.set_manifest({"version": "1.0.0", "url": update_server.zip_url, "sha256": "x"})
    launcher.manifest_url = update_server.manifest_url

    messages: list[str] = []
    launcher.run(on_status=messages.append)

    assert any("Güncel sürümdesiniz" in m for m in messages)


def test_download_update_reports_progress(launcher, update_server):
    payload = _make_zip_bytes({"main.exe": b"x" * (1 << 20)})  # 1 chunk'tan büyük olsun
    update_server.set_zip_bytes(payload)

    progress_calls: list[tuple[int, int]] = []
    launcher.download_update(
        update_server.zip_url, on_progress=lambda downloaded, total: progress_calls.append((downloaded, total))
    )

    assert len(progress_calls) >= 1
    last_downloaded, last_total = progress_calls[-1]
    assert last_downloaded == len(payload)
    assert last_total == len(payload)
