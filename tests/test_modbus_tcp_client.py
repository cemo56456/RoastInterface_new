"""
test_modbus_tcp_client.py — ModbusTCPClient protokol testleri.

PLC'ye hiç bağlanmadan, soketi taklit ederek (mock) bayt seviyesinde
istek/yanıt doğruluğunu kontrol eder.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock

import pytest

from services.modbus_tcp_client import ModbusTCPClient


def make_connected_client() -> ModbusTCPClient:
    """Soketi zaten 'bağlıymış gibi' ayarlanmış bir client döner."""
    client = ModbusTCPClient(host="127.0.0.1", port=502, unit_id=1)
    client.sock = MagicMock()
    return client


def mbap_response(tid: int, unit_id: int, pdu: bytes) -> bytes:
    """Verilen PDU'yu geçerli bir MBAP başlığıyla sarar (test yanıtı üretmek için)."""
    length = len(pdu) + 1
    return struct.pack(">HHHB", tid, 0, length, unit_id) + pdu


def queue_response(client: ModbusTCPClient, full_response: bytes):
    """
    Gerçek bir soket recv(n) çağrısında en fazla n bayt döner — MagicMock
    bunu otomatik yapmadığı için, yanıtı gerçek client'ın okuma sırasına
    uygun şekilde iki parçaya (7 baytlık MBAP başlığı + kalan gövde)
    bölüp side_effect olarak veriyoruz.
    """
    header, body = full_response[:7], full_response[7:]
    client.sock.recv.side_effect = [header, body]


# --------------------------------------------------------------------- #
# read_holding_n (FC=0x03)
# --------------------------------------------------------------------- #

def test_read_holding_n_success():
    client = make_connected_client()
    client._tid = 0  # ilk transaction id = 1 olacak

    # PLC'nin MW2020'de 245 (24.5°C x10) döndürdüğünü simüle ediyoruz
    fc03_pdu = struct.pack(">BBH", 0x03, 2, 245)  # fc, byte_count, value
    full = mbap_response(tid=1, unit_id=1, pdu=fc03_pdu)
    queue_response(client, full)

    values, err = client.read_holding_n(2020, 1)

    assert err is None
    assert values == [245]


def test_read_holding_n_multiple_registers():
    client = make_connected_client()
    client._tid = 0

    fc03_pdu = struct.pack(">BB", 0x03, 6) + struct.pack(">3H", 10, 20, 30)
    queue_response(client, mbap_response(1, 1, fc03_pdu))

    values, err = client.read_holding_n(100, 3)

    assert err is None
    assert values == [10, 20, 30]


def test_read_holding_n_rejects_invalid_qty():
    client = make_connected_client()
    values, err = client.read_holding_n(100, 0)
    assert values is None
    assert "1..125" in err


def test_read_holding_n_modbus_exception_response():
    client = make_connected_client()
    client._tid = 0

    # FC=0x03 | 0x80 = 0x83 -> Illegal Data Address (kod 2)
    exception_pdu = struct.pack(">BB", 0x83, 2)
    queue_response(client, mbap_response(1, 1, exception_pdu))

    values, err = client.read_holding_n(9999, 1)

    assert values is None
    assert "Illegal Data Address" in err


def test_read_holding_n_wrong_transaction_id_is_rejected():
    client = make_connected_client()
    client._tid = 0

    fc03_pdu = struct.pack(">BBH", 0x03, 2, 1)
    # PLC yanlışlıkla farklı bir tid ile cevap veriyor
    queue_response(client, mbap_response(tid=999, unit_id=1, pdu=fc03_pdu))

    values, err = client.read_holding_n(2020, 1)

    assert values is None
    assert "Transaction id" in err


# --------------------------------------------------------------------- #
# write_single_register (FC=0x06)
# --------------------------------------------------------------------- #

def test_write_single_register_success():
    client = make_connected_client()
    client._tid = 0

    # PLC, FC06 yanıtında genelde aynı reg+value'yu yansıtır (echo)
    echo_pdu = struct.pack(">BHH", 0x06, 2020, 250)
    queue_response(client, mbap_response(1, 1, echo_pdu))

    ok, err = client.write_single_register(2020, 250)

    assert ok is True
    assert err is None

    # Gönderilen PDU'nun doğru byte'ları içerdiğini de doğrulayalım
    sent_bytes = client.sock.sendall.call_args[0][0]
    sent_pdu = sent_bytes[7:]  # ilk 7 bayt MBAP başlığı
    assert sent_pdu == struct.pack(">BHH", 0x06, 2020, 250)


# --------------------------------------------------------------------- #
# write_single_coil (FC=0x05)
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("value,expected_raw", [(True, 0xFF00), (False, 0x0000)])
def test_write_single_coil(value, expected_raw):
    client = make_connected_client()
    client._tid = 0

    echo_pdu = struct.pack(">BHH", 0x05, 50, expected_raw)
    queue_response(client, mbap_response(1, 1, echo_pdu))

    ok, err = client.write_single_coil(50, value)

    assert ok is True
    sent_pdu = client.sock.sendall.call_args[0][0][7:]
    assert sent_pdu == struct.pack(">BHH", 0x05, 50, expected_raw)


# --------------------------------------------------------------------- #
# read_coils (FC=0x01)
# --------------------------------------------------------------------- #

def test_read_coils_decodes_bits_correctly():
    client = make_connected_client()
    client._tid = 0

    # 10 coil istiyoruz, 2 bayt döner. İlk bayt: 0b00000101 -> coil0=1, coil2=1
    fc01_pdu = struct.pack(">BB", 0x01, 2) + bytes([0b00000101, 0b00000000])
    queue_response(client, mbap_response(1, 1, fc01_pdu))

    bits, err = client.read_coils(50, 10)

    assert err is None
    assert len(bits) == 10
    assert bits[0] is True
    assert bits[1] is False
    assert bits[2] is True
    assert all(b is False for b in bits[3:])


def test_read_coils_rejects_invalid_qty():
    client = make_connected_client()
    bits, err = client.read_coils(0, 0)
    assert bits is None
    assert "1..2000" in err


# --------------------------------------------------------------------- #
# Bağlantı hataları
# --------------------------------------------------------------------- #

def test_connect_failure_returns_false(monkeypatch):
    client = ModbusTCPClient(host="10.255.255.1", port=502, timeout=0.1)

    def fail_connect(*args, **kwargs):
        raise OSError("bağlantı reddedildi")

    monkeypatch.setattr("socket.create_connection", fail_connect)

    assert client.connect() is False
    assert client.is_connected is False


def test_read_when_disconnected_and_reconnect_fails(monkeypatch):
    client = ModbusTCPClient(host="10.255.255.1", port=502, timeout=0.1)

    monkeypatch.setattr(
        "socket.create_connection",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no route")),
    )

    values, err = client.read_holding_n(2020, 1)

    assert values is None
    assert "PLC bağlantısı yok" in err


def test_broken_connection_during_read_closes_socket():
    client = make_connected_client()
    client.sock.recv.side_effect = OSError("bağlantı koptu")

    values, err = client.read_holding_n(2020, 1)

    assert values is None
    assert client.is_connected is False  # close() çağrılmış olmalı