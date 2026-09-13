"""
dev_release_update.py — "Yeni bir sürüm yayınlamayı" simüle eder
(geliştirme/test amaçlı).

Gerçek hayatta bu, GitHub Releases'e (ya da başka bir sunucuya) bir zip +
version.json yüklemek olurdu. Gerçek sunucu henüz yok, bu yüzden bu araç
aynı işi yerelde yapıyor: mevcut kaynak kodu paketler, `update_server_simulator`
ile serve eder ve launcher'ın buna karşı test edilebilmesi için
`LAUNCHER_MANIFEST_URL` olarak kullanılacak adresi ekrana yazar.

Kullanım:
    1. Önce bir kere:  python tools/dev_seed_app.py
       (app/ klasörünü "1.0.0 kurulu" gibi başlangıç durumuna getirir)
    2. Kodda istediğin değişikliği yap (main.py, screens/, ... fark etmez)
    3. python tools/dev_release_update.py 1.1.0
       (mevcut kodu "1.1.0" olarak paketleyip sahte sunucudan yayınlar)
    4. Başka bir terminalde:
       $env:LAUNCHER_MANIFEST_URL = "<yukarıda basılan adres>"
       .\\.venv\\Scripts\\python.exe launcher_app.py
       → launcher "1.1.0 bulundu" deyip indirecek, app/'a uygulayacak,
         version.txt'yi güncelleyecek ve GÜNCELLENMİŞ main.py'yi açacak.

Ctrl+C ile durur.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.dev_app_builder import build_runtime_zip  # noqa: E402
from tools.update_server_simulator import UpdateServerSimulator  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Kullanım: python tools/dev_release_update.py <sürüm, ör. 1.1.0>")
        sys.exit(1)

    version = sys.argv[1]

    zip_path = PROJECT_ROOT / "_dev_release.zip"
    build_runtime_zip(PROJECT_ROOT, zip_path)
    payload = zip_path.read_bytes()
    zip_path.unlink()

    sha256 = hashlib.sha256(payload).hexdigest()

    sim = UpdateServerSimulator(host="127.0.0.1", port=0)
    sim.set_zip_bytes(payload)
    sim.set_manifest({"version": version, "url": sim.zip_url, "sha256": sha256})
    sim.start()

    print(f"[dev_release_update] '{version}' sürümü yayınlandı (kaynak: mevcut proje kodu)")
    print(f"[dev_release_update] Manifest adresi: {sim.manifest_url}")
    print("[dev_release_update] Başka bir terminalde şunu çalıştır:")
    print(f'    $env:LAUNCHER_MANIFEST_URL = "{sim.manifest_url}"')
    print(r"    .\.venv\Scripts\python.exe launcher_app.py")
    print("[dev_release_update] Durdurmak için Ctrl+C")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
        print("\n[dev_release_update] Durduruldu.")


if __name__ == "__main__":
    main()
