"""
temp_graph.py — Basit, bağımlılıksız kayan sıcaklık grafiği.

kivy_garden.graph gibi ek bir paket gerektirmiyor; sadece Kivy'nin
canvas/Line ilkelleriyle son N örneği bir çizgi olarak çiziyor. Endüstriyel
bir dokunmatik panelde tek bir eğrinin (bean temp) canlı görülmesi
yeterli — eksen etiketi, ölçek çizgisi gibi detaylar bilinçli olarak
eklenmedi (henüz istenmedi, YAGNI).
"""

from __future__ import annotations

from kivy.graphics import Color, Line
from kivy.uix.widget import Widget


class TempGraph(Widget):
    def __init__(self, min_value: float = 0.0, max_value: float = 250.0, max_points: int = 180, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self.max_points = max_points
        self._points: list[float] = []
        self.bind(pos=self._redraw, size=self._redraw)

    def add_point(self, value: float) -> None:
        self._points.append(value)
        if len(self._points) > self.max_points:
            self._points.pop(0)
        self._redraw()

    def clear(self) -> None:
        self._points.clear()
        self._redraw()

    def _redraw(self, *args) -> None:
        self.canvas.clear()
        with self.canvas:
            Color(1, 1, 1, 0.15)
            Line(rectangle=(self.x, self.y, self.width, self.height))

            if len(self._points) < 2:
                return

            Color(0.95, 0.55, 0.15, 1)
            span = max(self.max_value - self.min_value, 1e-6)
            n = len(self._points)
            step_x = self.width / max(n - 1, 1)

            line_points: list[float] = []
            for i, value in enumerate(self._points):
                ratio = (value - self.min_value) / span
                ratio = min(max(ratio, 0.0), 1.0)
                x = self.x + i * step_x
                y = self.y + ratio * self.height
                line_points.extend([x, y])

            Line(points=line_points, width=1.5)
