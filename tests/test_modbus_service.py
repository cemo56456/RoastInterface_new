"""
test_modbus_service.py — ModbusService testleri.

İki kategori test var:
1. Gerçek modbus_simulator.py'ye karşı bütünleşik testler (subscribe/get_values/write akışı gerçekten çalışıyor mu).
2. PLC ULAŞILAMAZ durumdayken bile public metotların ANINDA döndüğünü
   (yani ana thread'i asla bloklamadığını) ölçen zamanlama testleri —
   bu, eski projedeki lag sorununun bu sefer gerçekten çözüldüğünü kanıtlar.
"""

from __future__ import annotations

import threading
import time

import pytest

from services.modbus_service import ModbusService
from tools.modbus_simulator import ModbusSimulator


_next_test_port = [15100]  # her teste ayrı port ver, TIME_WAIT/yarış durumlarını önle


@pytest.fixture
def running_simulator():
    """Gerçek bir Modbus TCP simülatörünü ayrı bir thread'de ayağa kaldırır."""
    _next_test_port[0] += 1
    port = _next_test_port[0]

    sim = ModbusSimulator(host="127.0.0.1", port=port, unit_id=1)
    sim.start()
    time.sleep(0.2)  # sunucunun dinlemeye başlaması için kısa bir bekleme
    sim.test_port = port  # testlerin okuyabilmesi için
    yield sim
    sim.stop()


# --------------------------------------------------------------------- #
# Bütünleşik testler (gerçek simülatöre karşı)
# --------------------------------------------------------------------- #

def test_subscribe_and_get_values_updates_over_time(running_simulator):
    service = ModbusService(host="127.0.0.1", port=running_simulator.test_port, unit_id=1, timeout=1.0)
    service.start()
    try:
        service.subscribe("live_block", start_reg=2020, qty=3, interval=0.2)

        # İlk anda henüz okuma yapılmamış olabilir
        deadline = time.monotonic() + 2.0
        values = None
        while time.monotonic() < deadline:
            values, err = service.get_values("live_block")
            if values is not None:
                break
            time.sleep(0.05)

        assert values is not None, "Abonelik zamanında hiç veri gelmedi"
        assert values[0] == 240  # simülatörün başlangıç set sıcaklığı
        assert service.is_connected is True
    finally:
        service.stop()


def test_write_register_is_applied_and_callback_fires(running_simulator):
    service = ModbusService(host="127.0.0.1", port=running_simulator.test_port, unit_id=1, timeout=1.0)
    service.start()
    try:
        # Bağlantının kurulmasını bekle
        deadline = time.monotonic() + 2.0
        while not service.is_connected and time.monotonic() < deadline:
            time.sleep(0.05)
        assert service.is_connected

        result = {}

        def on_done(ok, err):
            result["ok"] = ok
            result["err"] = err

        service.write_register(2020, 999, callback=on_done)

        # Callback, ancak process_events() çağrıldığında (ana thread simülasyonu) çalışır
        deadline = time.monotonic() + 2.0
        while "ok" not in result and time.monotonic() < deadline:
            service.process_events()
            time.sleep(0.05)

        assert result.get("ok") is True
        assert result.get("err") is None

        service.subscribe("check", start_reg=2020, qty=1, interval=0.1)
        deadline = time.monotonic() + 2.0
        values = None
        while time.monotonic() < deadline:
            values, _ = service.get_values("check")
            if values == [999]:
                break
            time.sleep(0.05)
        assert values == [999], "Yazılan değer PLC'de gerçekten güncellenmemiş"
    finally:
        service.stop()


# --------------------------------------------------------------------- #
# Bloklamama (non-blocking) testleri — asıl kanıtlamak istediğimiz şey
# --------------------------------------------------------------------- #

def test_public_methods_never_block_when_plc_unreachable():
    """
    Ulaşılamaz bir IP'ye (10.255.255.1, non-routable test adresi) bağlanmaya
    çalışan bir servis kurup, arka plan thread'i bağlantı timeout'unda
    beklerken bile is_connected/get_values/subscribe/write_register gibi
    public metotların ANINDA (birkaç milisaniyede) döndüğünü doğrular.

    Bu, eski projedeki 'PLC yoksa arayüz donuyor' sorununun yeni mimaride
    var olmadığının doğrudan kanıtıdır.
    """
    service = ModbusService(
        host="10.255.255.1",  # RFC 5737 tarzı, yanıt vermeyen test adresi
        port=502,
        timeout=1.5,          # bilerek "yavaş" bir timeout - arka plan thread bunu bekleyecek
        min_backoff=1.0,
    )
    service.start()

    try:
        # Arka plan thread şu anda connect() içinde 1.5 saniye boyunca
        # bloklanmış olabilir. Buna rağmen ana thread tarafındaki
        # çağrıların hepsi anında dönmeli.
        for _ in range(20):
            t0 = time.perf_counter()

            service.subscribe("x", 2020, 3, interval=1.0)
            _ = service.is_connected
            _ = service.get_values("x")
            service.write_register(2020, 1)
            service.process_events()

            elapsed = time.perf_counter() - t0
            assert elapsed < 0.05, (
                f"Public metot {elapsed*1000:.1f}ms sürdü — ana thread bloklanıyor!"
            )
            time.sleep(0.02)

        assert service.is_connected is False  # gerçekten bağlanamadı, bekleneni doğrula
    finally:
        service.stop()


def test_get_values_returns_immediately_before_any_subscription():
    """Hiç abone olunmamışken get_values() çağırmak, bekletmeden hata döner."""
    service = ModbusService(host="10.255.255.1", port=502, timeout=1.5)
    # start() bile çağırmadan, tamamen izole şekilde test ediyoruz
    values, err = service.get_values("hic-olmayan-abonelik")
    assert values is None
    assert "abonelik" in err.lower()


def test_stop_terminates_background_thread_cleanly(running_simulator):
    service = ModbusService(host="127.0.0.1", port=running_simulator.test_port, unit_id=1, timeout=1.0)
    service.start()
    time.sleep(0.3)
    service.stop()

    # Thread gerçekten sonlanmış olmalı (join zaten stop() içinde yapılıyor,
    # burada ekstra olarak "çalışan thread sayısı arttı mı" diye bakıyoruz)
    alive_names = [t.name for t in threading.enumerate() if t.is_alive()]
    assert not any("Thread" in n and t.daemon for n, t in
                   [(t.name, t) for t in threading.enumerate() if t.name == service._thread.name])