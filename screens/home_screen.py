"""
home_screen.py — Ana ekran.

Kritik mimari gereksinim: bu ekran PLC bağlantısını HİÇ beklemeden açılır.
Bağlantı durumu ve canlı sıcaklıklar sadece ModbusService'in önceden
abone olunmuş, anında dönen `get_values()` çağrısıyla okunur — ana thread
hiçbir zaman soket G/Ç'si için beklemez.

Yerleşim, kullanıcının orijinal uygulamadan paylaştığı ekran görüntüsünü
izliyor: sol panelde sıcaklıklar, sağ panelde süre/Rate of Rise/başlat
butonu SABİT kalıyor; ortadaki grafik + alt sekmeler (Profil/Manuel
Kontrol/Make Profile) değişiyor — ayrı, tam ekran navigasyon değil.

Bilinçli olarak EKLENMEDİ (bkz. handoff.md):
- Drying/Maillard/Development faz süreleri — hangi sıcaklık eşiklerinde
  bir fazdan diğerine geçildiği register haritası/kullanıcı onayı
  netleşmeden tahmin edilmedi.
- Exhaust/Burner/Airflow gösterge (%) değerleri — bunlar gerçek PLC
  register'larına ihtiyaç duyuyor, henüz bilinmiyor.

Roasting Time ve Rate of Rise ise register'a ihtiyaç DUYMUYOR (sadece
"Profile Start" butonu + bean temp geçmişinden hesaplanıyor, bkz.
services/roast_session.py) — bu yüzden şimdiden gerçek/işlevsel olarak
eklendi.
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from config import settings
from screens.base_screen import BaseRoasterScreen
from services.roast_session import RoastSession, format_duration
from widgets.multi_temp_graph import MultiTempGraph

# (alan_anahtari, görünen ad, birim) — sırayla orijinal ekrandaki "PROFILE"
# tablosunun satırları. Her satırın Değer + Exhaust% + Alev% sütunu var.
PROFILE_FIELDS = [
    ("drop_down_temp", "Drop Down Temp", "°C"),
    ("hopper_open_time_sec", "Hopper Open Time", "sn"),
    ("chaffing_sec", "Chaffing", "sn"),
    ("chaffing_time_sec", "Chaffing Time", "sn"),
    ("first_crack_temp", "First Crack Temp", "°C"),
    ("second_crack_temp", "Second Crack Temp", "°C"),
    ("drop_out_temp", "Drop Out Temp", "°C"),
]

KV = """
<Card@BoxLayout>:
    padding: 16
    spacing: 10
    canvas.before:
        Color:
            rgba: 0.12, 0.12, 0.15, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [14,]

<FieldInput@TextInput>:
    multiline: False
    size_hint_y: None
    height: 36
    font_size: 14
    background_color: 0.18, 0.18, 0.21, 1
    foreground_color: 1, 1, 1, 1
    cursor_color: 1, 1, 1, 1
    padding: 8, 8

<HomeScreen>:
    canvas.before:
        Color:
            rgba: 0.07, 0.07, 0.09, 1
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: "horizontal"
        padding: 16
        spacing: 16

        # -------------------- Sol panel: sıcaklıklar (SABİT) -------------------- #
        Card:
            orientation: "vertical"
            size_hint_x: 0.22

            BoxLayout:
                size_hint_y: None
                height: 28
                spacing: 8

                Widget:
                    size_hint: None, None
                    size: 18, 18
                    canvas:
                        Color:
                            rgba: (0.2, 0.85, 0.3, 1) if root.plc_connected else (0.6, 0.15, 0.15, 1)
                        Ellipse:
                            pos: self.pos
                            size: self.size

                Label:
                    text: "PLC Bağlı" if root.plc_connected else "PLC Bağlı Değil"
                    color: 1, 1, 1, 1
                    font_size: 14
                    halign: "left"
                    valign: "middle"
                    text_size: self.size

            Widget:
                size_hint_y: None
                height: 8

            Label:
                text: "Set Value"
                color: 0.6, 0.65, 0.7, 1
                font_size: 14
                size_hint_y: None
                height: 20
            Label:
                text: root.set_temp_text
                color: 0.6, 0.8, 1, 1
                font_size: 26
                bold: True
                size_hint_y: None
                height: 36

            Label:
                text: "Bean Temp"
                color: 0.6, 0.65, 0.7, 1
                font_size: 14
                size_hint_y: None
                height: 20
            Label:
                text: root.bean_temp_text
                color: 1, 0.65, 0.2, 1
                font_size: 44
                bold: True
                size_hint_y: None
                height: 56

            Label:
                text: "Egzoz Sıcaklığı"
                color: 0.6, 0.65, 0.7, 1
                font_size: 14
                size_hint_y: None
                height: 20
            Label:
                text: root.exhaust_temp_text
                color: 0.85, 0.85, 0.85, 1
                font_size: 26
                bold: True
                size_hint_y: None
                height: 36

            Widget:

        # -------------------- Orta: grafik + sekmeler -------------------- #
        BoxLayout:
            orientation: "vertical"
            spacing: 16

            Card:
                id: graph_slot
                size_hint_y: 0.55

            TabbedPanel:
                do_default_tab: False
                tab_width: self.width / 3
                background_color: 0.12, 0.12, 0.15, 1

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

                TabbedPanelItem:
                    text: "Make Profile"

                    BoxLayout:
                        id: make_profile_slot
                        orientation: "vertical"
                        padding: 12
                        spacing: 8

        # -------------------- Sağ panel: süre / RoR / başlat (SABİT) -------------------- #
        Card:
            orientation: "vertical"
            size_hint_x: 0.22

            Label:
                text: "Roasting Time"
                color: 0.6, 0.65, 0.7, 1
                font_size: 14
                size_hint_y: None
                height: 20
            Label:
                text: root.roasting_time_text
                color: 1, 0.8, 0.3, 1
                font_size: 30
                bold: True
                size_hint_y: None
                height: 40

            Widget:
                size_hint_y: None
                height: 12

            Label:
                text: "Rate Of Rise"
                color: 0.6, 0.65, 0.7, 1
                font_size: 14
                size_hint_y: None
                height: 20
            Label:
                text: root.ror_text
                color: 1, 0.4, 0.3, 1
                font_size: 24
                bold: True
                size_hint_y: None
                height: 32
            Label:
                text: root.ror_max_text
                color: 0.5, 0.5, 0.5, 1
                font_size: 13
                size_hint_y: None
                height: 18

            Widget:

            Button:
                text: "Durdur" if root.roast_active else "Profile Start"
                size_hint_y: None
                height: 52
                background_color: (0.7, 0.2, 0.2, 1) if root.roast_active else (0.2, 0.6, 0.3, 1)
                on_release: root.toggle_roast()
"""

Builder.load_string(KV)


class HomeScreen(BaseRoasterScreen):
    plc_connected = BooleanProperty(False)
    set_temp_text = StringProperty("--")
    bean_temp_text = StringProperty("--")
    exhaust_temp_text = StringProperty("--")
    roasting_time_text = StringProperty("00:00")
    ror_text = StringProperty("0.0 °C/dk")
    ror_max_text = StringProperty("0.0 °C/dk max")
    roast_active = BooleanProperty(False)

    _poll_event = None
    _graph: MultiTempGraph | None = None
    _roast_session: RoastSession | None = None
    _profile_inputs: dict[str, dict[str, TextInput]] | None = None
    _profile_name_input: TextInput | None = None

    def on_kv_post(self, base_widget) -> None:
        self._graph = MultiTempGraph(min_value=0.0, max_value=300.0)
        self._graph.add_series("SET", (0.9, 0.25, 0.25, 1))
        self._graph.add_series("EXH", (0.9, 0.75, 0.2, 1))
        self._graph.add_series("ROR", (0.3, 0.85, 0.4, 1))
        self._graph.add_series("BT", (1, 0.55, 0.15, 1), hero=True)
        self.ids.graph_slot.add_widget(self._graph)

        self._roast_session = RoastSession()
        self._build_make_profile_tab()

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

    # ------------------------------------------------------------------ #
    # Canlı veri döngüsü
    # ------------------------------------------------------------------ #

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

        session = self._roast_session
        ror = 0.0
        if session is not None and session.is_active:
            session.feed_sample(bean_temp)
            ror = session.rate_of_rise()
            self.roasting_time_text = format_duration(session.elapsed())
            self.ror_text = f"{ror:.1f} °C/dk"
            self.ror_max_text = f"{session.max_rate_of_rise:.1f} °C/dk max"

        if self._graph is not None:
            self._graph.add_point("SET", set_temp)
            self._graph.add_point("BT", bean_temp)
            self._graph.add_point("EXH", exhaust_temp)
            self._graph.add_point("ROR", ror * 5)  # orijinal ekrandaki gibi "ROR x5" ölçeği

    def toggle_roast(self) -> None:
        session = self._roast_session
        if session is None:
            return

        if session.is_active:
            session.stop()
            self.roast_active = False
            self._toast("Kavurma durduruldu")
        else:
            session.start()
            if self._graph is not None:
                self._graph.clear()
            self.roast_active = True
            self.roasting_time_text = "00:00"
            self.ror_text = "0.0 °C/dk"
            self.ror_max_text = "0.0 °C/dk max"
            self._toast("Kavurma başladı")

    # ------------------------------------------------------------------ #
    # Profil sekmesi
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Make Profile sekmesi
    # ------------------------------------------------------------------ #

    def _build_make_profile_tab(self) -> None:
        container = self.ids.make_profile_slot

        name_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        name_row.add_widget(Label(text="Profil Adı", size_hint_x=0.3, color=(1, 1, 1, 1)))
        self._profile_name_input = TextInput(multiline=False, background_color=(0.18, 0.18, 0.21, 1),
                                              foreground_color=(1, 1, 1, 1))
        name_row.add_widget(self._profile_name_input)
        container.add_widget(name_row)

        grid = GridLayout(cols=4, size_hint_y=None, spacing=6, row_default_height=36)
        grid.bind(minimum_height=grid.setter("height"))

        for header in ("Aşama", "Değer", "Exhaust %", "Alev %"):
            grid.add_widget(Label(text=header, bold=True, color=(0.8, 0.8, 0.8, 1), size_hint_y=None, height=32))

        self._profile_inputs = {}
        for key, label, unit in PROFILE_FIELDS:
            grid.add_widget(Label(text=f"{label} ({unit})", color=(1, 1, 1, 1), size_hint_y=None, height=36,
                                   halign="left", valign="middle", text_size=(220, 36)))

            value_input = TextInput(text="0", multiline=False, size_hint_y=None, height=36,
                                     background_color=(0.18, 0.18, 0.21, 1), foreground_color=(1, 1, 1, 1))
            exhaust_input = TextInput(text="0", multiline=False, size_hint_y=None, height=36,
                                       background_color=(0.18, 0.18, 0.21, 1), foreground_color=(1, 1, 1, 1))
            flame_input = TextInput(text="0", multiline=False, size_hint_y=None, height=36,
                                     background_color=(0.18, 0.18, 0.21, 1), foreground_color=(1, 1, 1, 1))

            grid.add_widget(value_input)
            grid.add_widget(exhaust_input)
            grid.add_widget(flame_input)

            self._profile_inputs[key] = {
                "value": value_input,
                "exhaust_pct": exhaust_input,
                "flame_pct": flame_input,
            }

        container.add_widget(grid)

        save_btn = Button(text="Profili Kaydet", size_hint_y=None, height=48)
        save_btn.bind(on_release=lambda _btn: self._save_profile_from_form())
        container.add_widget(save_btn)

    def _save_profile_from_form(self) -> None:
        name = (self._profile_name_input.text or "").strip()
        if not name:
            self._toast("Profil adı boş olamaz")
            return

        data: dict[str, dict[str, float]] = {}
        for key, label, _unit in PROFILE_FIELDS:
            inputs = self._profile_inputs[key]
            try:
                data[key] = {
                    "value": float(inputs["value"].text),
                    "exhaust_pct": float(inputs["exhaust_pct"].text),
                    "flame_pct": float(inputs["flame_pct"].text),
                }
            except ValueError:
                self._toast(f"Geçersiz sayı: {label}")
                return

        ok, err = self.profiles.save_profile(name, data)
        if not ok:
            self._toast(f"Kaydedilemedi: {err}")
            return

        self._toast(f"'{name}' kaydedildi")
        self.refresh_profiles()
