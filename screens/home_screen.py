"""
home_screen.py — Ana ekran.

Kritik mimari gereksinim: bu ekran PLC bağlantısını HİÇ beklemeden açılır.
Bağlantı durumu (`plc_connected`) sadece ModbusService.is_connected'ı
periyodik olarak (Clock ile) okuyarak güncellenir — bu okuma da anında
döner (bkz. services/modbus_service.py), yani ana thread hiçbir zaman
soket G/Ç'si için beklemez.
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty

from screens.base_screen import BaseRoasterScreen

KV = """
<HomeScreen>:
    canvas.before:
        Color:
            rgba: 0.07, 0.07, 0.09, 1
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: "vertical"
        padding: 24
        spacing: 20

        BoxLayout:
            size_hint_y: None
            height: 40
            spacing: 12

            Widget:
                size_hint: None, None
                size: 24, 24
                canvas:
                    Color:
                        rgba: (0.2, 0.85, 0.3, 1) if root.plc_connected else (0.6, 0.15, 0.15, 1)
                    Ellipse:
                        pos: self.pos
                        size: self.size

            Label:
                text: "PLC Bağlı" if root.plc_connected else "PLC Bağlı Değil"
                color: 1, 1, 1, 1
                font_size: 18
                halign: "left"
                valign: "middle"
                text_size: self.size

        Label:
            text: "RoasterInterface v2"
            font_size: 32
            bold: True
            color: 1, 1, 1, 1
            size_hint_y: None
            height: 60

        Button:
            text: "Profil (yakında)"
            size_hint_y: None
            height: 56
            disabled: True

        Button:
            text: "Canlı Kavurma (yakında)"
            size_hint_y: None
            height: 56
            disabled: True

        Button:
            text: "Manuel Kontrol (yakında)"
            size_hint_y: None
            height: 56
            disabled: True

        Widget:
"""

Builder.load_string(KV)


class HomeScreen(BaseRoasterScreen):
    plc_connected = BooleanProperty(False)

    _poll_event = None

    def on_enter(self, *args) -> None:
        self._poll_event = Clock.schedule_interval(self._poll_connection, 0.2)

    def on_leave(self, *args) -> None:
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None

    def _poll_connection(self, dt: float) -> None:
        self.plc_connected = self.modbus.is_connected
