"""
modbus_service.py — ModbusTCPClient'ı arka plan thread'inde saran servis.

Amaç: Kivy'nin ana thread'i asla soket G/Ç'si ile bloklanmasın. Bu yüzden
buradaki hiçbir public metot (subscribe/get_values/write_register/
write_coil/is_connected/process_events) doğrudan soket işlemi yapmaz —
sadece paylaşılan duruma hızlıca okuma/yazma yapıp anında döner. Gerçek
Modbus trafiği sadece _run_loop() içinde, ayrı bir arka plan thread'inde
yürütülür.

Callback'ler (write_register/write_coil) kasıtlı olarak arka plan
thread'inden değil, ana thread process_events() çağırdığında tetiklenir —
böylece Kivy widget'ları callback içinde güvenle güncellenebilir.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from services.modbus_tcp_client import ModbusTCPClient


@dataclass
class _Subscription:
    start_reg: int
    qty: int
    interval: float
    last_read: float = 0.0
    values: list[int] | None = None
    error: str | None = None


class ModbusService:
    def __init__(
        self,
        host: str = "192.168.1.50",
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 1.5,
        min_backoff: float = 0.5,
        max_backoff: float = 10.0,
    ):
        self._client = ModbusTCPClient(host=host, port=port, unit_id=unit_id, timeout=timeout)
        self._min_backoff = min_backoff
        self._max_backoff = max_backoff

        self._lock = threading.Lock()
        self._subscriptions: dict[str, _Subscription] = {}
        self._is_connected = False

        self._write_queue: queue.Queue = queue.Queue()
        self._callback_queue: queue.Queue = queue.Queue()

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # Yaşam döngüsü
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="ModbusServiceThread", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._client.close()

    # ------------------------------------------------------------------ #
    # Public, ANINDA dönen API (ana thread'den çağrılır)
    # ------------------------------------------------------------------ #

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    def subscribe(self, name: str, start_reg: int, qty: int, interval: float = 1.0) -> None:
        with self._lock:
            self._subscriptions[name] = _Subscription(
                start_reg=start_reg, qty=qty, interval=interval
            )

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            self._subscriptions.pop(name, None)

    def get_values(self, name: str) -> tuple[list[int] | None, str | None]:
        with self._lock:
            sub = self._subscriptions.get(name)
            if sub is None:
                return None, f"'{name}' için abonelik yok"
            return sub.values, sub.error

    def write_register(self, reg: int, value: int, callback=None) -> None:
        self._write_queue.put(("register", reg, value, callback))

    def write_coil(self, coil: int, value: bool, callback=None) -> None:
        self._write_queue.put(("coil", coil, value, callback))

    def process_events(self) -> None:
        """Ana thread'den periyodik (ör. Kivy Clock ile) çağrılmalı; kuyruğa
        alınmış write callback'lerini burada, çağıran thread üzerinde tetikler."""
        while True:
            try:
                callback, ok, err = self._callback_queue.get_nowait()
            except queue.Empty:
                break
            if callback is not None:
                callback(ok, err)

    # ------------------------------------------------------------------ #
    # Arka plan thread — tüm soket G/Ç'si sadece burada yapılır
    # ------------------------------------------------------------------ #

    def _run_loop(self) -> None:
        backoff = self._min_backoff
        while not self._stop_event.is_set():
            if not self._client.is_connected:
                if self._client.connect():
                    with self._lock:
                        self._is_connected = True
                    backoff = self._min_backoff
                else:
                    with self._lock:
                        self._is_connected = False
                    self._stop_event.wait(backoff)
                    backoff = min(backoff * 2, self._max_backoff)
                    continue

            self._process_writes()
            self._process_subscriptions()
            self._stop_event.wait(0.05)

    def _process_writes(self) -> None:
        while True:
            try:
                kind, addr, value, callback = self._write_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "register":
                ok, err = self._client.write_single_register(addr, value)
            else:
                ok, err = self._client.write_single_coil(addr, value)

            if not ok:
                with self._lock:
                    self._is_connected = self._client.is_connected

            if callback is not None:
                self._callback_queue.put((callback, ok, err))

    def _process_subscriptions(self) -> None:
        now = time.monotonic()
        with self._lock:
            due = [
                (name, sub.start_reg, sub.qty)
                for name, sub in self._subscriptions.items()
                if now - sub.last_read >= sub.interval
            ]

        for name, start_reg, qty in due:
            values, err = self._client.read_holding_n(start_reg, qty)
            with self._lock:
                current = self._subscriptions.get(name)
                if current is None:
                    continue
                if values is not None:
                    current.values = values
                current.error = err
                current.last_read = now
                if err is not None:
                    self._is_connected = self._client.is_connected
