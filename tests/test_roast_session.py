"""
test_roast_session.py — RoastSession testleri.

Gerçek zamanı beklememek için sahte (fake) bir saat enjekte ediliyor.
"""

from __future__ import annotations

from services.roast_session import RoastSession, format_duration


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def test_not_active_before_start():
    session = RoastSession(clock=FakeClock())
    assert session.is_active is False
    assert session.elapsed() == 0.0
    assert session.rate_of_rise() == 0.0


def test_elapsed_increases_after_start():
    clock = FakeClock()
    session = RoastSession(clock=clock)

    session.start()
    assert session.is_active is True
    assert session.elapsed() == 0.0

    clock.advance(42.0)
    assert session.elapsed() == 42.0


def test_stop_resets_active_state():
    clock = FakeClock()
    session = RoastSession(clock=clock)
    session.start()
    clock.advance(10.0)

    session.stop()

    assert session.is_active is False
    assert session.elapsed() == 0.0


def test_feed_sample_ignored_when_not_active():
    session = RoastSession(clock=FakeClock())
    session.feed_sample(200.0)
    assert session.rate_of_rise() == 0.0


def test_rate_of_rise_basic_calculation():
    clock = FakeClock()
    session = RoastSession(clock=clock)
    session.start()

    session.feed_sample(200.0)
    clock.advance(30.0)
    session.feed_sample(215.0)

    # (215-200)*10 / 30s -> 15 derece / 30s -> dakikada 30 derece
    assert session.rate_of_rise() == 30.0


def test_rate_of_rise_zero_with_single_sample():
    clock = FakeClock()
    session = RoastSession(clock=clock)
    session.start()
    session.feed_sample(200.0)

    assert session.rate_of_rise() == 0.0


def test_old_samples_outside_window_are_trimmed():
    clock = FakeClock()
    session = RoastSession(ror_window=60.0, clock=clock)
    session.start()

    session.feed_sample(200.0)  # t=0
    clock.advance(90.0)  # pencerenin çok dışında kalacak
    session.feed_sample(200.0)  # t=90, hiç artış yok
    clock.advance(10.0)
    session.feed_sample(210.0)  # t=100, son 60s içinde artış var

    # İlk örnek (t=0) pencere dışında kalmalı; sadece t=90->100 arası hesaba katılmalı
    # (210-200)*60/10 = 60 derece/dk
    assert session.rate_of_rise() == 60.0


def test_max_rate_of_rise_tracks_peak_and_survives_drop():
    clock = FakeClock()
    session = RoastSession(ror_window=60.0, clock=clock)
    session.start()

    session.feed_sample(200.0)
    clock.advance(10.0)
    session.feed_sample(220.0)  # hızlı artış -> yüksek RoR
    peak = session.rate_of_rise()
    assert peak > 0

    clock.advance(10.0)
    session.feed_sample(220.0)  # artış durdu -> RoR düşer
    assert session.rate_of_rise() < peak
    assert session.max_rate_of_rise == peak


def test_start_again_resets_previous_session_state():
    clock = FakeClock()
    session = RoastSession(clock=clock)

    session.start()
    session.feed_sample(200.0)
    clock.advance(10.0)
    session.feed_sample(230.0)
    assert session.max_rate_of_rise > 0

    clock.advance(100.0)
    session.start()  # yeni kavurma

    assert session.elapsed() == 0.0
    assert session.max_rate_of_rise == 0.0
    assert session.rate_of_rise() == 0.0


def test_format_duration_under_a_minute():
    assert format_duration(7) == "00:07"


def test_format_duration_minutes_and_seconds():
    assert format_duration(125) == "02:05"


def test_format_duration_includes_hours_when_needed():
    assert format_duration(3661) == "01:01:01"
