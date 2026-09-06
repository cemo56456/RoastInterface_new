"""
modbus_tcp_client.py — Modbus TCP istemcisi (RoasterInterface v2).

Tek sınıfta toplanmış, üçüncü parti kütüphane (pymodbus vb.) kullanmayan,
soket üzerinde ham Modbus TCP protokolü konuşan istemci.

Desteklenen fonksiyon kodları:
    FC=0x01  Read Coils
    FC=0x03  Read Holding Registers
    FC=0x05  Write Single Coil
    FC=0x06  Write Single Register

Tasarım notu: Tüm okuma/yazma metotları (result, error) şeklinde bir tuple
döner. `error is None` ise işlem başarılıdır. Böylece çağıran taraf
exception yakalamak zorunda kalmadan hatayı kontrol edebilir — bu,
Kivy'nin ana thread'i yerine bir arka plan thread'inden çağrılacağı için
(ModbusService) özellikle önemli: thread içinde patlayan bir exception
sessizce kaybolabilir, ama dönüş değeri her zaman kontrol edilir.
"""

from __future__ import annotations

import socket
import struct
import threading


class ModbusException(Exception):
    """PLC'nin döndürdüğü bir Modbus exception yanıtını (hata kodu) temsil eder."""

    def __init__(self, function_code: int, exception_code: int):
        self.function_code = function_code
        self.exception_code = exception_code
        super().__init__(
            f"Modbus exception: FC=0x{function_code:02X}, "
            f"kod={exception_code} ({self._describe(exception_code)})"
        )

    @staticmethod
    def _describe(code: int) -> str:
        return {
            1: "Illegal Function",
            2: "Illegal Data Address",
            3: "Illegal Data Value",
            4: "Slave Device Failure",
            6: "Slave Device Busy",
        }.get(code, "Bilinmeyen hata")


class ModbusTCPClient:
    """Ethernet üzerinden bir PLC'ye Modbus TCP ile bağlanan istemci."""

    def __init__(
        self,
        host: str = "192.168.1.50",
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 1.5,
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout

        self.sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._tid = 0  # transaction id sayacı (0..0xFFFF)

    # ------------------------------------------------------------------ #
    # Bağlantı yönetimi
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        """PLC'ye TCP soketi açar. Başarılıysa True, değilse False döner."""
        self.close()
        try:
            self.sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            return True
        except OSError:
            self.sock = None
            return False

    def close(self) -> None:
        """Soketi güvenli şekilde kapatır."""
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    @property
    def is_connected(self) -> bool:
        return self.sock is not None

    def _ensure_connected(self) -> bool:
        if self.sock is None:
            return self.connect()
        return True

    # ------------------------------------------------------------------ #
    # Dahili yardımcılar
    # ------------------------------------------------------------------ #

    def _next_transaction_id(self) -> int:
        self._tid = (self._tid + 1) % 0x10000
        if self._tid == 0:
            self._tid = 1
        return self._tid

    def _recv_exact(self, n: int) -> bytes | None:
        """Soketten tam olarak n bayt okur; okuyamazsa None döner."""
        buf = b""
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None  # bağlantı karşı taraftan kapanmış
            buf += chunk
        return buf

    def _send_pdu(self, pdu: bytes) -> tuple[bytes | None, str | None]:
        """
        MBAP başlığını kurup PDU ile birlikte gönderir, yanıtı okur ve
        temel doğrulamaları (transaction id, protokol id, unit id, Modbus
        exception biti) yapar. Başarılıysa (pdu_yaniti, None) döner.
        """
        if not self._ensure_connected():
            return None, "PLC bağlantısı yok"

        tid = self._next_transaction_id()
        mbap = struct.pack(">HHHB", tid, 0, len(pdu) + 1, self.unit_id)

        try:
            self.sock.sendall(mbap + pdu)
        except OSError as e:
            self.close()
            return None, f"Gönderim hatası: {e}"

        header = self._recv_exact(7)
        if header is None:
            self.close()
            return None, "Yanıt başlığı okunamadı (bağlantı koptu)"

        resp_tid, resp_proto, resp_len, resp_unit = struct.unpack(">HHHB", header)
        if resp_tid != tid:
            return None, f"Transaction id uyuşmuyor (beklenen {tid}, gelen {resp_tid})"
        if resp_proto != 0:
            return None, f"Beklenmeyen protokol id: {resp_proto}"
        if resp_unit != self.unit_id:
            return None, f"Unit id uyuşmuyor (beklenen {self.unit_id}, gelen {resp_unit})"

        body = self._recv_exact(resp_len - 1)
        if body is None:
            self.close()
            return None, "Yanıt gövdesi okunamadı (bağlantı koptu)"

        function_code = body[0]
        if function_code & 0x80:  # en üst bit set ise Modbus exception yanıtı
            exception_code = body[1] if len(body) > 1 else 0
            return None, str(ModbusException(function_code & 0x7F, exception_code))

        return body, None

    # ------------------------------------------------------------------ #
    # Genel amaçlı okuma/yazma metotları
    # ------------------------------------------------------------------ #

    def read_holding_n(
        self, start_reg: int, qty: int
    ) -> tuple[list[int] | None, str | None]:
        """FC=0x03. `start_reg`'den başlayarak `qty` adet holding register okur."""
        if not (1 <= qty <= 125):
            return None, "qty 1..125 aralığında olmalı"

        with self._lock:
            pdu = struct.pack(">BHH", 0x03, start_reg, qty)
            body, err = self._send_pdu(pdu)
            if err:
                return None, err

            byte_count = body[1]
            data = body[2 : 2 + byte_count]
            if len(data) != byte_count:
                return None, "Yanıt uzunluğu beklenenle uyuşmuyor"

            values = list(struct.unpack(f">{qty}H", data))
            return values, None

    def write_single_register(
        self, reg: int, value: int
    ) -> tuple[bool, str | None]:
        """FC=0x06. Tek bir 16-bit register'a yazar."""
        with self._lock:
            pdu = struct.pack(">BHH", 0x06, reg, value & 0xFFFF)
            _, err = self._send_pdu(pdu)
            return (err is None), err

    def write_single_coil(
        self, coil_addr: int, value: bool
    ) -> tuple[bool, str | None]:
        """FC=0x05. Tek bir coil'e (boolean) yazar."""
        with self._lock:
            raw = 0xFF00 if value else 0x0000
            pdu = struct.pack(">BHH", 0x05, coil_addr, raw)
            _, err = self._send_pdu(pdu)
            return (err is None), err

    def read_coils(
        self, start_coil: int, qty: int
    ) -> tuple[list[bool] | None, str | None]:
        """FC=0x01. `start_coil`'den başlayarak `qty` adet coil okur."""
        if not (1 <= qty <= 2000):
            return None, "qty 1..2000 aralığında olmalı"

        with self._lock:
            pdu = struct.pack(">BHH", 0x01, start_coil, qty)
            body, err = self._send_pdu(pdu)
            if err:
                return None, err

            byte_count = body[1]
            data = body[2 : 2 + byte_count]
            if len(data) != byte_count:
                return None, "Yanıt uzunluğu beklenenle uyuşmuyor"

            bits: list[bool] = []
            for byte in data:
                for i in range(8):
                    bits.append(bool(byte & (1 << i)))
            return bits[:qty], None