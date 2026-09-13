"""
launcher_app.py — RoasterInterface güncelleme başlatıcısının görsel
(Kivy) giriş ekranı.

Gerçek güncelleme mantığı `launcher.py`'deki `Launcher` sınıfında — bu
dosya sadece onun üzerine ince bir görsel katman (`launcher.py` hiçbir
zaman `kivy` import etmiyor, bilinçli olarak). PyInstaller hedefi ve
masaüstü kısayolu artık bu dosyayı çalıştıracak.

Mimari kural (projenin geri kalanıyla aynı, bkz. services/modbus_service.py
+ screens/home_screen.py): `Launcher.run()` bir arka plan thread'inde
çalıştırılıyor ki asıl network/dosya G/Ç'si Kivy'nin ana thread'ini
bloklamasın. `on_status`/`on_progress` callback'leri widget'lara DOĞRUDAN
dokunmuyor — her biri `Clock.schedule_once` ile ana thread'e devrediyor.

Not: `main.exe` henüz paketlenmediği için (bkz. handoff.md) şu an
`config/settings.py`'deki `LAUNCHER_DEV_MAIN_SCRIPT` (varsayılan
"main.py") devrede — başarılı bir "başlatma" aslında `python main.py`
çalıştırıyor. Gerçek paketleme yapılınca bu ayar boşaltılmalı.
"""

from __future__ import annotations

import threading
from pathlib import Path

from kivy.config import Config

# bkz. main.py'deki aynı not — sağ tık simülasyonunu kapatıyoruz.
Config.set("input", "mouse", "mouse,multitouch_on_demand")

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

from config import settings
from launcher import Launcher

KV = """
<LauncherScreen>:
    canvas.before:
        Color:
            rgba: 0.07, 0.07, 0.09, 1
        Rectangle:
            pos: self.pos
            size: self.size

    orientation: "vertical"
    padding: 40
    spacing: 12

    Widget:

    Label:
        text: "RoasterInterface"
        font_size: 34
        bold: True
        color: 1, 0.55, 0.15, 1
        size_hint_y: None
        height: 48

    Label:
        text: root.version_text
        color: 0.6, 0.65, 0.7, 1
        font_size: 14
        size_hint_y: None
        height: 20

    Widget:
        size_hint_y: None
        height: 16

    Label:
        text: root.status_text
        color: 1, 1, 1, 1
        font_size: 16
        size_hint_y: None
        height: 28

    ProgressBar:
        max: 100
        value: root.progress_value
        opacity: 1 if root.progress_visible else 0
        size_hint_y: None
        height: 8

    Label:
        text: root.error_text
        color: 0.9, 0.3, 0.3, 1
        font_size: 13
        opacity: 1 if root.has_error else 0
        size_hint_y: None
        height: (24 if root.has_error else 0)

    Button:
        text: "Kapat"
        size_hint_y: None
        height: (44 if root.has_error else 0)
        opacity: 1 if root.has_error else 0
        disabled: not root.has_error
        on_release: root.close_requested()

    Widget:
"""

Builder.load_string(KV)


class LauncherScreen(BoxLayout):
    status_text = StringProperty("Başlatılıyor...")
    version_text = StringProperty("")
    progress_value = NumericProperty(0)
    progress_visible = BooleanProperty(False)
    error_text = StringProperty("")
    has_error = BooleanProperty(False)

    def close_requested(self) -> None:
        App.get_running_app().stop()


class LauncherApp(App):
    title = "RoasterInterface Başlatıcı"

    def build(self):
        self.screen = LauncherScreen()

        app_dir = Path(__file__).parent / settings.LAUNCHER_APP_DIR
        dev_main_script = None
        if settings.LAUNCHER_DEV_MAIN_SCRIPT:
            dev_main_script = Path(__file__).parent / settings.LAUNCHER_DEV_MAIN_SCRIPT

        self.launcher = Launcher(
            app_dir=app_dir,
            manifest_url=settings.LAUNCHER_MANIFEST_URL,
            timeout=settings.LAUNCHER_TIMEOUT,
            dev_main_script=dev_main_script,
        )
        self.screen.version_text = f"Sürüm: {self.launcher.get_local_version()}"

        threading.Thread(target=self._run_launcher, daemon=True).start()
        return self.screen

    # ------------------------------------------------------------------ #
    # Arka plan thread — Launcher.run() burada, ana thread'i bloklamadan
    # ------------------------------------------------------------------ #

    def _run_launcher(self) -> None:
        def on_status(message: str) -> None:
            Clock.schedule_once(lambda dt: self._apply_status(message))

        def on_progress(downloaded: int, total: int) -> None:
            Clock.schedule_once(lambda dt: self._apply_progress(downloaded, total))

        ok = self.launcher.run(on_status=on_status, on_progress=on_progress)
        Clock.schedule_once(lambda dt: self._finish(ok))

    # ------------------------------------------------------------------ #
    # Ana thread'de widget güncellemeleri
    # ------------------------------------------------------------------ #

    def _apply_status(self, message: str) -> None:
        self.screen.status_text = message
        if "indiriliyor" not in message.lower():
            self.screen.progress_visible = False

    def _apply_progress(self, downloaded: int, total: int) -> None:
        self.screen.progress_visible = True
        self.screen.progress_value = (downloaded * 100 / total) if total else 0

    def _finish(self, ok: bool) -> None:
        if ok:
            self.screen.status_text = "Başlatıldı"
            Clock.schedule_once(lambda dt: self.stop(), 0.6)
        else:
            self.screen.error_text = self.screen.status_text
            self.screen.has_error = True
            self.screen.status_text = "Başlatma başarısız"


if __name__ == "__main__":
    LauncherApp().run()
