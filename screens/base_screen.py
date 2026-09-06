"""
base_screen.py — Tüm ekranların ortak temel sınıfı.

Orijinal projede `_dark_popup`, `_toast`, `_get_modbus_client` gibi yardımcı
metotlar 4-5 dosyada ayrı ayrı kopyalanmıştı. v2'de bu tekilleştirme
BaseRoasterScreen üzerinden yapılıyor — yeni bir ekran bu yardımcılara
ihtiyaç duyduğunda kopyalamak yerine buradan miras alır.
"""

from __future__ import annotations

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen

from services.modbus_service import ModbusService


class BaseRoasterScreen(Screen):
    """Ortak yardımcıları ve `ModbusService` erişimini sağlayan temel ekran."""

    @property
    def modbus(self) -> ModbusService:
        """Çalışan App örneğinin ModbusService'ine erişim.

        Ekranlar servisi doğrudan kurmaz/tutmaz — tek bir örnek App
        seviyesinde yaşar, ekranlar sadece kullanır.
        """
        return App.get_running_app().modbus_service

    def _dark_popup(self, title: str, message: str, auto_dismiss: bool = True) -> Popup:
        """Koyu temalı, tek butonlu bir bilgi/uyarı popup'ı açar."""
        content = BoxLayout(orientation="vertical", padding=16, spacing=12)
        content.add_widget(Label(text=message, color=(1, 1, 1, 1)))

        close_btn = Button(text="Kapat", size_hint=(1, None), height=48)
        content.add_widget(close_btn)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.7, 0.5),
            auto_dismiss=auto_dismiss,
            title_color=(1, 1, 1, 1),
            separator_color=(0.2, 0.6, 1, 1),
            background_color=(0.1, 0.1, 0.12, 1),
        )
        close_btn.bind(on_release=popup.dismiss)
        popup.open()
        return popup

    def _toast(self, message: str, duration: float = 2.0) -> Popup:
        """Kısa süre görünüp kendiliğinden kapanan bilgi mesajı."""
        popup = Popup(
            title="",
            content=Label(text=message, color=(1, 1, 1, 1)),
            size_hint=(0.6, 0.15),
            auto_dismiss=True,
            separator_height=0,
            background_color=(0.1, 0.1, 0.12, 0.95),
        )
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), duration)
        return popup
