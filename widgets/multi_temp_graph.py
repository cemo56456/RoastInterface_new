"""
multi_temp_graph.py — Birden fazla seriyi (SET/BT/EXH/RoR) aynı eksende
çizen, bağımlılıksız (kivy_garden gerektirmeyen) kayan grafik.

Bean Temp (BT) "hero" seri olarak işaretlenebilir — altı hafif renkli bir
dolgu ile vurgulanır, diğer seriler sade çizgi olarak kalır. Eksen
etiketi/sayısal skala YOK — henüz istenmedi (YAGNI), sadece izleme amaçlı
bir grafik.
"""

from __future__ import annotations

from kivy.graphics import Color, Line, Mesh
from kivy.uix.widget import Widget


class MultiTempGraph(Widget):
    def __init__(self, min_value: float = 0.0, max_value: float = 300.0, max_points: int = 600, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self.max_points = max_points
        self._series: dict[str, dict] = {}
        self._hero: str | None = None
        self.bind(pos=self._redraw, size=self._redraw)

    def add_series(self, name: str, color: tuple[float, float, float, float], hero: bool = False) -> None:
        self._series[name] = {"color": color, "points": []}
        if hero:
            self._hero = name

    def add_point(self, name: str, value: float) -> None:
        series = self._series.get(name)
        if series is None:
            return
        points = series["points"]
        points.append(value)
        if len(points) > self.max_points:
            points.pop(0)
        self._redraw()

    def clear(self) -> None:
        for series in self._series.values():
            series["points"].clear()
        self._redraw()

    # ------------------------------------------------------------------ #

    def _value_to_y(self, value: float) -> float:
        span = max(self.max_value - self.min_value, 1e-6)
        ratio = (value - self.min_value) / span
        ratio = min(max(ratio, 0.0), 1.0)
        return self.y + ratio * self.height

    def _redraw(self, *args) -> None:
        self.canvas.clear()
        with self.canvas:
            self._draw_grid()
            for name, series in self._series.items():
                self._draw_series(series["points"], series["color"], filled=(name == self._hero))

    def _draw_grid(self) -> None:
        Color(1, 1, 1, 0.08)
        Line(rectangle=(self.x, self.y, self.width, self.height))
        for fraction in (0.25, 0.5, 0.75):
            y = self.y + self.height * fraction
            Line(points=[self.x, y, self.x + self.width, y], width=1)

    def _draw_series(self, values: list[float], color: tuple[float, float, float, float], filled: bool) -> None:
        if len(values) < 2:
            return

        n = len(values)
        step_x = self.width / max(n - 1, 1)
        line_points: list[float] = []
        for i, value in enumerate(values):
            x = self.x + i * step_x
            y = self._value_to_y(value)
            line_points.extend([x, y])

        if filled:
            self._draw_fill(line_points, color)

        Color(*color)
        Line(points=line_points, width=1.8)

    def _draw_fill(self, line_points: list[float], color: tuple[float, float, float, float]) -> None:
        """`line_points` altını tabana kadar yarı saydam bir Mesh ile doldurur.

        `triangle_strip` kullanılıyor (top/bottom çiftleri birbirini takip
        ediyor) — çizgi yukarı/aşağı dalgalansa bile üçgenler her zaman
        doğru şeritler oluşturur; `triangle_fan` tek bir merkez noktadan
        çizdiği için dalgalı eğrilerde kendini kesen üçgenler üretirdi.
        """
        n = len(line_points) // 2
        baseline_y = self.y

        vertices: list[float] = []
        for i in range(n):
            x, y = line_points[2 * i], line_points[2 * i + 1]
            vertices.extend([x, y, 0, 0])
            vertices.extend([x, baseline_y, 0, 0])

        indices = list(range(2 * n))

        r, g, b, _ = color
        Color(r, g, b, 0.18)
        Mesh(vertices=vertices, indices=indices, mode="triangle_strip")
