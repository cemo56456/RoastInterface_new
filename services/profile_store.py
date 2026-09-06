"""
profile_store.py — Kavurma profillerinin diskte JSON olarak saklanması.

Orijinal projede profil okuma/yazma/listeleme mantığı 3 ayrı ekrana
dağılmıştı (her biri kendi dosya I/O'sunu yapıyordu). v2'de bu tek bir
`ProfileStore` üzerinden tekilleştirildi.

Tasarım notu: Profilin içeriği (hangi parametrelerin olduğu — hedef
sıcaklık, menşei, zaman-sıcaklık eğrisi vb.) bilinçli olarak
`ProfileStore`'a gömülmedi; bir profil sadece isimlendirilmiş, serbest
biçimli bir JSON sözlüğüdür (`dict`). Kullanıcı arayüzü hangi alanları
gösterip düzenleteceğine kendi karar verir, `ProfileStore` sadece
okuma/yazma/listeleme/silme sağlar. Böylece profil şeması değiştiğinde bu
sınıfın değişmesi gerekmez.

Tüm metotlar, `ModbusTCPClient`'taki gibi (sonuç, hata) tuple'ı döner —
`hata is None` ise işlem başarılıdır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_VALID_NAME = re.compile(r"^[A-Za-z0-9_\- ÇçĞğİıÖöŞşÜü]{1,80}$")


class ProfileStore:
    """`profiles_dir` altında her profili `<isim>.json` olarak saklar."""

    def __init__(self, profiles_dir: str | Path = "profiles"):
        self.profiles_dir = Path(profiles_dir)

    def _path_for(self, name: str) -> tuple[Path | None, str | None]:
        if not _VALID_NAME.match(name):
            return None, (
                "Geçersiz profil adı: sadece harf, rakam, boşluk, '_' ve '-' "
                "kullanılabilir (1-80 karakter)"
            )
        return self.profiles_dir / f"{name}.json", None

    def list_profiles(self) -> tuple[list[str] | None, str | None]:
        """Kayıtlı profil isimlerini (uzantısız, alfabetik) döner."""
        if not self.profiles_dir.exists():
            return [], None
        try:
            names = sorted(p.stem for p in self.profiles_dir.glob("*.json"))
            return names, None
        except OSError as e:
            return None, f"Profil listesi okunamadı: {e}"

    def load_profile(self, name: str) -> tuple[dict | None, str | None]:
        path, err = self._path_for(name)
        if err:
            return None, err

        if not path.exists():
            return None, f"'{name}' adında bir profil yok"

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except OSError as e:
            return None, f"Profil okunamadı: {e}"
        except json.JSONDecodeError as e:
            return None, f"Profil dosyası bozuk (geçersiz JSON): {e}"

        if not isinstance(data, dict):
            return None, "Profil dosyası bir JSON nesnesi (dict) içermiyor"

        return data, None

    def save_profile(self, name: str, data: dict) -> tuple[bool, str | None]:
        path, err = self._path_for(name)
        if err:
            return False, err

        if not isinstance(data, dict):
            return False, "Profil verisi bir dict olmalı"

        try:
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".json.tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_path.replace(path)
        except OSError as e:
            return False, f"Profil yazılamadı: {e}"

        return True, None

    def delete_profile(self, name: str) -> tuple[bool, str | None]:
        path, err = self._path_for(name)
        if err:
            return False, err

        if not path.exists():
            return False, f"'{name}' adında bir profil yok"

        try:
            path.unlink()
        except OSError as e:
            return False, f"Profil silinemedi: {e}"

        return True, None
