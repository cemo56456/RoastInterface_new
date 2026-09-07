"""
home_screen.py — Ana ekran.

Kritik mimari gereksinim: bu ekran PLC bağlantısını HİÇ beklemeden açılır.
Bağlantı durumu ve canlı sıcaklıklar sadece ModbusService'in önceden
abone olunmuş, anında dönen `get_values()` çağrısıyla okunur — ana thread
hiçbir zaman soket G/Ç'si için beklemez.

Yerleşim, kullanıcının orijinal uygulamadan hatırladığı yapıyı izliyor:
sıcaklıklar + grafik SABİT bir üst alanda; Profil / Manuel Kontrol gibi
paneller bunun altında sekmelerle değişiyor (ayrı, tam ekran navigasyon
değil). "Süre" (kronometre) ve süreç aşaması (kurutma/sararma/ilk çatlak
vb.) göstergeleri, bunların hangi coil/register'a bağlı olduğu netleşene
kadar bilinçli olarak eklenmedi — bkz. handoff.md.
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.button import Button

from config import settings
from screens.base_screen import BaseRoasterScreen
from widgets.temp_graph import TempGraph

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
        padding: 20
        spacing: 16

        # -- Sabit üst alan: bağlantı durumu + sıcaklıklar + grafik -------- #

        BoxLayout:
            size_hint_y: None
            height: 36
            spacing: 12

            Widget:
                size_hint: None, None
                size: 22, 22
                canvas:
                    Color:
                        rgba: (0.2, 0.85, 0.3, 1) if root.plc_connected else (0.6, 0.15, 0.15, 1)
                    Ellipse:
                        pos: self.pos
                        size: self.size

            Label:
                text: "PLC Bağlı" if root.plc_connected else "PLC Bağlı Değil"
                color: 1, 1, 1, 1
                font_size: 16
                halign: "left"
                valign: "middle"
                text_size: self.size

        BoxLayout:
            size_hint_y: None
            height: 64
            spacing: 24

            Label:
                text: "Set: " + root.set_temp_text
                color: 0.6, 0.8, 1, 1
                font_size: 22
                bold: True

            Label:
                text: "Bean: " + root.bean_temp_text
                color: 1, 0.7, 0.3, 1
                font_size: 22
                bold: True

            Label:
                text: "Egzoz: " + root.exhaust_temp_text
                color: 0.8, 0.8, 0.8, 1
                font_size: 22
                bold: True

        BoxLayout:
            id: graph_slot
            size_hint_y: 0.45

        # -- Değişen alt panel: sekmeler ------------------------------------ #

        TabbedPanel:
            do_default_tab: False
            tab_width: self.width / 2

            TabbedPanelItem:
                text: "Profil"

                BoxLayout:
                    orientation: "vertical"
                    padding: 12
                    spacing: 8

                    Button:
                        text: "Listeyi Yenile"
                        size_hint_y: None
                        height: 44
                        on_release: root.refresh_profiles()

                    ScrollView:
                        BoxLayout:
                            id: profile_list
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                            spacing: 4

            TabbedPanelItem:
                text: "Manuel Kontrol"

                BoxLayout:
                    padding: 12

                    Label:
                        text: "Manuel kontrol butonları, gerçek register/coil haritası netleşince eklenecek."
                        color: 0.7, 0.7, 0.7, 1
                        halign: "center"
                        valign: "middle"
                        text_size: self.size
"""

Builder.load_string(KV)


class HomeScreen(BaseRoasterScreen):
    plc_connected = BooleanProperty(False)
    set_temp_text = StringProperty("--")
    bean_temp_text = StringProperty("--")
    exhaust_temp_text = StringProperty("--")

    _poll_event = None
    _graph: TempGraph | None = None

    def on_kv_post(self, base_widget) -> None:
        self._graph = TempGraph(min_value=0.0, max_value=250.0)
        self.ids.graph_slot.add_widget(self._graph)

    def on_enter(self, *args) -> None:
        self.modbus.subscribe(
            "home_live_temps",
            start_reg=settings.LIVE_TEMPS_START,
            qty=settings.LIVE_TEMPS_QTY,
            interval=1.0,
        )
        self.refresh_profiles()
        self._poll_event = Clock.schedule_interval(self._poll, 0.3)

    def on_leave(self, *args) -> None:
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None
        self.modbus.unsubscribe("home_live_temps")

    def _poll(self, dt: float) -> None:
        self.plc_connected = self.modbus.is_connected

        values, err = self.modbus.get_values("home_live_temps")
        if err is not None or values is None:
            self.set_temp_text = "--"
            self.bean_temp_text = "--"
            self.exhaust_temp_text = "--"
            return

        set_temp, bean_temp, exhaust_temp = (v / settings.TEMP_SCALE for v in values)
        self.set_temp_text = f"{set_temp:.1f}°C"
        self.bean_temp_text = f"{bean_temp:.1f}°C"
        self.exhaust_temp_text = f"{exhaust_temp:.1f}°C"

        if self._graph is not None:
            self._graph.add_point(bean_temp)

    def refresh_profiles(self) -> None:
        container = self.ids.profile_list
        container.clear_widgets()

        names, err = self.profiles.list_profiles()
        if err is not None:
            self._toast(f"Profil listesi okunamadı: {err}")
            return

        if not names:
            container.add_widget(Button(text="(Henüz profil yok)", size_hint_y=None, height=44, disabled=True))
            return

        for name in names:
            btn = Button(text=name, size_hint_y=None, height=44)
            btn.bind(on_release=lambda _btn, n=name: self._on_profile_selected(n))
            container.add_widget(btn)

    def _on_profile_selected(self, name: str) -> None:
        data, err = self.profiles.load_profile(name)
        if err is not None:
            self._toast(f"Profil okunamadı: {err}")
            return
        self._toast(f"'{name}' seçildi: {data}")
