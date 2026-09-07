"""
roast_session.py — Aktif kavurma oturumunun süresini ve Rate of Rise (RoR)
değerini hesaplar.

Bilinçli tasarım kararı: register haritasından TAMAMEN bağımsız. Sadece
"Profile Start" butonuna basıldığı an ile beslenen bean temp örneklerinden
hesaplanıyor — PLC'den ek bir register/coil gerekmiyor. Bu yüzden gerçek
register haritası netleşmeden bile kullanılabilir (bkz. handoff.md).

RoR = son `ror_window` saniyedeki bean temp artışının dakika başına
karşılığı (°C/dakika) — kahve kavurma yazılımlarında yaygın bir yöntem.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Sample:
    t: float
    bean_temp: float


class RoastSession:
    def __init__(self, ror_window: float = 60.0, clock=time.monotonic):
        self._ror_window = ror_window
        self._clock = clock
        self._start_time: float | None = None
        self._samples: list[_Sample] = []
        self._max_ror: float = 0.0

    @property
    def is_active(self) -> bool:
        return self._start_time is not None

    def start(self) -> None:
        self._start_time = self._clock()
        self._samples.clear()
        self._max_ror = 0.0

    def stop(self) -> None:
        self._start_time = None

    def elapsed(self) -> float:
        if self._start_time is None:
            return 0.0
        return self._clock() - self._start_time

    def feed_sample(self, bean_temp: float) -> None:
        """Yeni bir bean temp örneği ekler. Oturum aktif değilse yok sayılır."""
        if self._start_time is None:
            return

        now = self._clock()
        self._samples.append(_Sample(now, bean_temp))

        cutoff = now - self._ror_window
        while len(self._samples) > 1 and self._samples[0].t < cutoff:
            self._samples.pop(0)

        self._max_ror = max(self._max_ror, self._compute_ror())

    def rate_of_rise(self) -> float:
        """°C/dakika. Yeterli örnek yoksa 0.0 döner."""
        return self._compute_ror()

    @property
    def max_rate_of_rise(self) -> float:
        return self._max_ror

    def _compute_ror(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        first, last = self._samples[0], self._samples[-1]
        dt = last.t - first.t
        if dt <= 0:
            return 0.0
        return (last.bean_temp - first.bean_temp) * (60.0 / dt)


def format_duration(seconds: float) -> str:
    """`012` -> `00:12`, `3661` -> `01:01:01` (bir saati geçince saat de gösterilir)."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
