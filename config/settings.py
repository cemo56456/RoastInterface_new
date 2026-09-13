"""
settings.py — Merkezi yapılandırma: PLC bağlantı bilgileri ve register
sabitleri.

**Register adresleri şu an YER TUTUCUDUR** (tools/modbus_simulator.py ile
aynı: MW2020-2022). Kullanıcı gerçek register haritasını (muhtemelen
MW580-609 aralığında, bkz. handoff.md "Dikkat edilmesi gerekenler")
`RoasterInterface_Fonksiyon_Referansi.md`'den bulup verdiğinde sadece bu
dosya güncellenecek — kodun geri kalanı bu sabitleri kullandığı için
değişmeyecek.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------- #
# PLC bağlantısı
# --------------------------------------------------------------------- #

MODBUS_HOST = os.environ.get("MODBUS_HOST", "192.168.1.50")
MODBUS_PORT = int(os.environ.get("MODBUS_PORT", "502"))
MODBUS_UNIT_ID = int(os.environ.get("MODBUS_UNIT_ID", "1"))
MODBUS_TIMEOUT = float(os.environ.get("MODBUS_TIMEOUT", "1.5"))

# --------------------------------------------------------------------- #
# Sıcaklık register'ları — YER TUTUCU, bkz. yukarıdaki not
# --------------------------------------------------------------------- #

REG_SET_TEMP = 2020
REG_BEAN_TEMP = 2021
REG_EXHAUST_TEMP = 2022

# Üçü ardışık olduğu için tek okumada alınabiliyor (bkz. ModbusService.subscribe)
LIVE_TEMPS_START = REG_SET_TEMP
LIVE_TEMPS_QTY = 3

# PLC sıcaklıkları x10 ölçekli gönderiyor (ör. 205 -> 20.5°C)
TEMP_SCALE = 10

# --------------------------------------------------------------------- #
# Profil dosyaları
# --------------------------------------------------------------------- #

PROFILES_DIR = os.environ.get("PROFILES_DIR", "profiles")

# --------------------------------------------------------------------- #
# Launcher / OTA güncelleme
# --------------------------------------------------------------------- #

# YER TUTUCU — kullanıcının henüz gerçek bir güncelleme sunucusu yok.
# Sunucu hazır olduğunda sadece bu satır değişecek.
LAUNCHER_MANIFEST_URL = os.environ.get(
    "LAUNCHER_MANIFEST_URL", "https://ORNEK-SUNUCUNUZ/roasterinterface/version.json"
)
LAUNCHER_TIMEOUT = float(os.environ.get("LAUNCHER_TIMEOUT", "5.0"))

# Ana uygulamanın (main.exe) kurulu olduğu klasör — launcher'ın kendi
# konumuna göre relatif.
LAUNCHER_APP_DIR = os.environ.get("LAUNCHER_APP_DIR", "app")
