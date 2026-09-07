"""
main.py — RoasterInterface v2 ana uygulaması.

Mimari kural: App.build() ASLA PLC bağlantısını beklemez. ModbusService
arka plan thread'inde kendi kendine bağlanmayı dener/yeniden dener;
ana thread (Kivy) sadece anında dönen public metotları kullanır.

Bağlantı/register sabitleri `config/settings.py`'den okunuyor.
"""

from __future__ import annotations

from kivy.config import Config

# Kivy varsayılan olarak sağ tıkı "ikinci parmak" gibi simüle edip ekranda
# kırmızı bir daire çiziyor (masaüstünde çoklu dokunmayı test edebilmek
# için). Bu, gerçek PLC bağlantı LED'imizle karışıyor ve dokunmatik panel
# hedefli bu uygulamada zaten bir işe yaramıyor; kapatıyoruz. Window
# oluşturulmadan önce ayarlanmalı, bu yüzden diğer kivy importlarından önce.
Config.set("input", "mouse", "mouse,multitouch_on_demand")

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager

from config import settings
from screens.home_screen import HomeScreen
from services.modbus_service import ModbusService
from services.profile_store import ProfileStore


class RoasterApp(App):
    title = "RoasterInterface v2"

    def build(self):
        self.modbus_service = ModbusService(
            host=settings.MODBUS_HOST,
            port=settings.MODBUS_PORT,
            unit_id=settings.MODBUS_UNIT_ID,
            timeout=settings.MODBUS_TIMEOUT,
        )
        self.modbus_service.start()

        self.profile_store = ProfileStore(profiles_dir=settings.PROFILES_DIR)

        Clock.schedule_interval(lambda dt: self.modbus_service.process_events(), 0.1)

        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        return sm

    def on_stop(self):
        self.modbus_service.stop()


if __name__ == "__main__":
    RoasterApp().run()
