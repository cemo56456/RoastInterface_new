"""
main.py — RoasterInterface v2 ana uygulaması.

Mimari kural: App.build() ASLA PLC bağlantısını beklemez. ModbusService
arka plan thread'inde kendi kendine bağlanmayı dener/yeniden dener;
ana thread (Kivy) sadece anında dönen public metotları kullanır.

Host/port şu an ortam değişkenlerinden okunuyor. Bu geçici bir çözüm —
sıradaki adımlarda (bkz. handoff.md) `config/settings.py` + `.env`
üzerinden merkezi bir yapılandırmaya taşınacak.
"""

from __future__ import annotations

import os

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

from screens.home_screen import HomeScreen
from services.modbus_service import ModbusService


class RoasterApp(App):
    title = "RoasterInterface v2"

    def build(self):
        host = os.environ.get("MODBUS_HOST", "192.168.1.50")
        port = int(os.environ.get("MODBUS_PORT", "502"))

        self.modbus_service = ModbusService(host=host, port=port, unit_id=1, timeout=1.5)
        self.modbus_service.start()

        Clock.schedule_interval(lambda dt: self.modbus_service.process_events(), 0.1)

        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        return sm

    def on_stop(self):
        self.modbus_service.stop()


if __name__ == "__main__":
    RoasterApp().run()
