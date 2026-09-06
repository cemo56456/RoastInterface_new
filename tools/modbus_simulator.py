"""
modbus_simulator.py — Basit Modbus TCP PLC simülatörü (geliştirme/test amaçlı).

Gerçek PLC olmadan ModbusTCPClient'ı (ve ileride ModbusService'i) uçtan
uca test edebilmek için. Sadece Python standart kütüphanesini kullanır,
hiçbir üçüncü parti paket gerektirmez.

Kullanım:
    python tools/modbus_simulator.py                  # 127.0.0.1:1502
    python tools/modbus_simulator.py 0.0.0.0 502       # farklı host/port

Desteklenen fonksiyon kodları: FC01 (Read Coils), FC03 (Read Holding
Registers), FC05 (Write Single Coil), FC06 (Write Single Register).

Gerçekçilik için: MW2021 (bean/çekirdek sıcaklığı) arka planda yavaşça
artırılır — böylece live_roast tarzı bir ekranı da simülatöre karşı
test edebilirsiniz.
"""

from __future__ import annotations

import socket
import struct
import sys
import threading
import time


class ModbusSimulator:
    def __init__(self, host: str = "127.0.0.1", port: int = 1502, unit_id: int = 1):
        self.host = host
        self.port = port
        self.unit_id = unit_id

        self.holding_registers: dict[int, int] = {}
        self.coils: dict[int, bool] = {}
        self._lock = threading.Lock()
        self._running = False

        # RoasterInterface'teki gerçek register haritasına benzer
        # gerçekçi başlangıç değerleri:
        self.holding_registers[2020] = 240  # set sıcaklığı x10 -> 24.0°C
        self.holding_registers[2021] = 235  # bean/çekirdek sıcaklığı x10
        self.holding_registers[2022] = 180  # egzoz sıcaklığı x10

    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._serve, daemon=True).start()
        threading.Thread(target=self._simulate_roast, daemon=True).start()

    def stop(self) -> None:
        self._running = False

    def _simulate_roast(self) -> None:
        """Bean sıcaklığını yavaşça yükseltip gerçek bir kavurmayı taklit eder."""
        while self._running:
            with self._lock:
                bt = self.holding_registers.get(2021, 235)
                if bt < 2100:  # 210°C tavan
                    self.holding_registers[2021] = bt + 1
            time.sleep(1)

    # ------------------------------------------------------------------ #
    # TCP sunucu döngüsü
    # ------------------------------------------------------------------ #

    def _serve(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(5)
        srv.settimeout(1.0)
        print(f"[sim] Modbus simülatörü {self.host}:{self.port} üzerinde dinliyor "
              f"(unit_id={self.unit_id})")

        while self._running:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            threading.Thread(
                target=self._handle_client, args=(conn, addr), daemon=True
            ).start()
        srv.close()

    def _handle_client(self, conn: socket.socket, addr) -> None:
        print(f"[sim] İstemci bağlandı: {addr}")
        with conn:
            conn.settimeout(30.0)
            while self._running:
                header = self._recv_exact(conn, 7)
                if header is None:
                    break
                tid, proto, length, unit = struct.unpack(">HHHB", header)
                pdu = self._recv_exact(conn, length - 1)
                if pdu is None:
                    break

                response_pdu = self._handle_pdu(pdu)
                resp_header = struct.pack(">HHHB", tid, 0, len(response_pdu) + 1, unit)
                try:
                    conn.sendall(resp_header + response_pdu)
                except OSError:
                    break
        print(f"[sim] İstemci ayrıldı: {addr}")

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> bytes | None:
        buf = b""
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf

    # ------------------------------------------------------------------ #
    # Modbus fonksiyon kodlarını işleme
    # ------------------------------------------------------------------ #

    def _handle_pdu(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        with self._lock:
            if fc == 0x03:  # Read Holding Registers
                start, qty = struct.unpack(">HH", pdu[1:5])
                values = [self.holding_registers.get(start + i, 0) for i in range(qty)]
                data = struct.pack(f">{qty}H", *values)
                return struct.pack(">BB", 0x03, len(data)) + data

            elif fc == 0x06:  # Write Single Register
                reg, value = struct.unpack(">HH", pdu[1:5])
                self.holding_registers[reg] = value
                print(f"[sim] YAZILDI: MW{reg} = {value}")
                return pdu  # PLC'ler FC06'da isteği aynen yansıtır (echo)

            elif fc == 0x05:  # Write Single Coil
                coil, raw = struct.unpack(">HH", pdu[1:5])
                self.coils[coil] = raw == 0xFF00
                print(f"[sim] YAZILDI: Coil{coil} = {self.coils[coil]}")
                return pdu

            elif fc == 0x01:  # Read Coils
                start, qty = struct.unpack(">HH", pdu[1:5])
                bits = [self.coils.get(start + i, False) for i in range(qty)]
                byte_count = (qty + 7) // 8
                data = bytearray(byte_count)
                for i, bit in enumerate(bits):
                    if bit:
                        data[i // 8] |= 1 << (i % 8)
                return struct.pack(">BB", 0x01, byte_count) + bytes(data)

            else:  # desteklenmeyen fonksiyon kodu -> Modbus exception
                return struct.pack(">BB", fc | 0x80, 0x01)  # Illegal Function


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 1502

    sim = ModbusSimulator(host=host, port=port)
    sim.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[sim] Kapatılıyor...")
        sim.stop()