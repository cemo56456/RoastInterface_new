# RoasterInterface v2 — Devir Teslim Notu (Claude ile yapılan planlama oturumundan)

Bu doküman, Claude (claude.ai) ile RoasterInterface'in sıfırdan yeniden yazımını
planlarken alınan kararları ve bugüne kadar yazılıp **gerçekten test edilmiş**
kodu özetler. Amaç: Claude Code buradan devam ederken aynı mimariyi bozmadan
ilerlemesi.

## Bağlam

Orijinal proje (`ergungozek-design/RoasterInterface`) incelendi; şu sorunlar
tespit edildi ve v2'de bilinçli olarak çözülüyor:

1. **Senkron Modbus çağrıları Kivy'nin ana thread'ini bloke ediyordu** — PLC
   koptuğunda/yavaşladığında tüm arayüz donuyordu, Home ekranına bile giriş
   gecikiyordu. → v2'de `ModbusService` bunu arka plan thread'inde çözüyor.
2. Kod tabanında `_eski` (eski) son ekli ölü fonksiyonlar, kopyalanmış yardımcı
   metotlar (`_dark_popup`, `_toast`, `_get_modbus_client` gibi 4-5 dosyada
   tekrar eden kod) vardı. → v2'de `BaseRoasterScreen` ile tekilleştirilecek
   (henüz yazılmadı, bkz. "Sırada ne var").
3. MQTT kimlik bilgileri koda gömülüydü. → v2'de `.env` + `config/settings.py`
   üzerinden okunacak (henüz yazılmadı).
4. `read_coils` fonksiyonu yanlışlıkla sınıfın dışında tanımlıydı. → v2'de
   düzeltildi, sınıfın içinde.

## Alınan mimari kararlar

- **RTU (seri port) desteği YOK ve OLMAYACAK** — kullanıcı bunu net olarak
  belirtti. Sadece Modbus TCP kullanılıyor.
- **`ModbusClientBase` gibi bir soyut ara sınıf YOK, bilinçli olarak** —
  kullanıcı "tek sınıf, daha basit" seçeneğini tercih etti. Test edilebilirlik
  için soyutlama yerine doğrudan `client.sock`'u mock'lama yöntemi kullanıldı
  (bkz. `tests/test_modbus_tcp_client.py`).
- **Register/coil sabitleri merkezi bir `config/settings.py`'de toplanacak**
  (henüz yazılmadı) — orijinal projede aynı sabitler (MW580, MW615 vb.) 2-3
  dosyada ayrı ayrı tanımlıydı, bu tekrar edilmeyecek.
- **Launcher ayrı bir bileşen olarak planlandı** (OTA güncelleme için) —
  `launcher/launcher.py` iskeleti yazıldı (bu depoya dahil, ama detaylandırılmadı).
  `version.json` manifest + SHA-256 doğrulama + rollback mantığı var.
- **Offline giriş**: Home ekranı PLC bağlantısını hiç beklemeden açılmalı.
  `ModbusService` bunu mimari olarak garanti ediyor (aşağıya bakın).

## Bitmiş ve test edilmiş parçalar

### `services/modbus_tcp_client.py`
Tek sınıf, `ModbusTCPClient`. FC01 (read coils), FC03 (read holding registers),
FC05 (write single coil), FC06 (write single register) destekliyor. Hiçbir
üçüncü parti Modbus kütüphanesi kullanmıyor (ham soket + struct).

`tests/test_modbus_tcp_client.py` — 13 test, hepsi geçiyor. Mock soketle
byte-seviyesinde protokol doğruluğu, Modbus exception yanıtları, transaction
id uyuşmazlığı, bağlantı kopması senaryoları kapsanıyor.

### `services/modbus_service.py`
`ModbusTCPClient`'ı arka plan thread'inde saran servis. **Hiçbir public
metodu soket I/O yapmaz** — `subscribe()`/`get_values()`/`write_register()`/
`write_coil()`/`is_connected` hepsi anında döner (cache okuma veya kuyruğa
ekleme). Gerçek soket işi sadece `_run_loop()` içinde, arka plan thread'inde
yapılıyor. Exponential backoff ile yeniden bağlanma var (`min_backoff`/
`max_backoff`).

`tests/test_modbus_service.py` — 5 test. En kritik olanı
`test_public_methods_never_block_when_plc_unreachable`: ulaşılamayan bir IP'ye
bağlanmaya çalışırken bile public metotların <50ms'de döndüğünü 20 kez ölçerek
kanıtlıyor. Bu, orijinal projedeki lag sorununun bu mimaride kökten çözüldüğünü
doğrulayan test.

### `tools/modbus_simulator.py`
Gerçek PLC olmadan geliştirme/test için bağımsız bir Modbus TCP sunucusu.
FC01/03/05/06 destekliyor, MW2021'i (bean temp) arka planda yavaşça artırarak
gerçek bir kavurmayı taklit ediyor. `python tools/modbus_simulator.py` ile
çalıştırılır, uygulama/testler `127.0.0.1:1502` (veya belirtilen port) hedef
gösterilerek buna karşı denenebilir. **Uygulamanın kendisine dahil değil**,
sadece geliştirme aracı — PyInstaller paketine girmemeli.

### `launcher.py`
OTA güncelleme akışının iskeleti (henüz tam entegre/test edilmedi):
`get_local_version → fetch_remote_manifest → download_update →
verify_checksum → apply_update → launch_main_app`, hata durumunda
`rollback()`. Ana uygulamanın `onedir` (tek klasör) modunda paketlenmesini
varsayıyor, `onefile` değil — çünkü güncelleme klasör üzerine zip açarak
yapılıyor. (Not: dosya köke `launcher.py` olarak taşındı, `launcher/`
klasörü altında değil.)

### `screens/base_screen.py`, `screens/home_screen.py`, `main.py`
**2026-09-06 oturumunda yazıldı.** `BaseRoasterScreen`, orijinal projede
tekrar eden `_dark_popup`/`_toast` yardımcılarını tekilleştiriyor ve
`App.get_running_app().modbus_service` üzerinden tek bir `ModbusService`
örneğine erişim sağlıyor. `HomeScreen`, `plc_connected` (BooleanProperty)
alanını `Clock.schedule_interval` ile 0.2s'de bir `modbus.is_connected`
okuyarak günceller — bu okuma anında döner, asla soket beklemez.

**Gerçek pencerede doğrulandı** (Python 3.11 + Kivy 2.3.1, proje kökünde
`.venv`): `RoasterApp.build()` ulaşılamayan bir PLC IP'sine karşı bile
~12ms'de dönüyor (offline giriş lag yapmıyor, mimari kanıtlandı) ve
simülatöre karşı ~1.5s içinde `is_connected` `True` oluyor. Ekran
görüntüsü otomasyonu bu ortamda (etkileşimli masaüstü oturumu olmadığı
için) siyah çıktı veriyor — pikselsel görsel doğrulama kullanıcı
tarafından `python main.py` çalıştırılarak elle yapılmalı, ama davranışsal
kanıt (zamanlama + `is_connected` değeri) tam.

**Önemli bulgu:** Bu oturuma devredilen depoda `services/modbus_service.py`
dosyası fiilen YOKTU — `handoff.md` bunu "bitmiş ve test edilmiş" olarak
işaretliyordu ve `tests/test_modbus_service.py` bu dosyayı import ediyordu,
ama dosyanın kendisi diskte yoktu (muhtemelen claude.ai'den yerel projeye
aktarım sırasında kayboldu). Test dosyasındaki beklenen arayüze bakılarak
yeniden yazıldı; 18/18 test (5 modbus_service + 13 modbus_tcp_client)
şu an geçiyor. **Ders:** bundan sonra "bitti" diye işaretlenen bir parçayı
kullanmadan önce dosyanın gerçekten diskte olduğunu doğrulayın.

**Ortam notu:** Kivy'nin Windows bağımlılıkları (`kivy_deps.sdl2_dev` vb.)
sistemdeki varsayılan Python 3.14 için henüz derlenmemiş. Bu yüzden proje
kökünde Python 3.11 ile bir `.venv` oluşturuldu (`kivy`, `pytest`, `requests`
kurulu). Testler ve uygulama bundan sonra bu venv ile çalıştırılmalı:
`.\.venv\Scripts\python.exe -m pytest` / `.\.venv\Scripts\python.exe main.py`.

**Küçük düzeltme (aynı oturum):** Kivy varsayılan olarak sağ tıkı "ikinci
parmak" gibi simüle edip ekranda kırmızı bir daire çiziyor (masaüstünde
çoklu dokunma testi için); bu bizim gerçek PLC LED'imizle karışıyordu ve
dokunmatik panel hedefli bu uygulamada zaten işe yaramıyor. `main.py`'de
`Config.set("input", "mouse", "mouse,multitouch_on_demand")` ile kapatıldı
(diğer kivy importlarından önce olmalı).

### `services/profile_store.py`
**2026-09-06 oturumunda yazıldı.** `ProfileStore`, profilleri
`profiles/<isim>.json` olarak saklar (okuma/yazma/listeleme/silme).
**Bilinçli tasarım kararı:** profil içeriğinin şeması (hangi alanlar —
menşei, pişirme sıcaklığı, zaman-sıcaklık eğrisi vb.) `ProfileStore`'a
gömülü DEĞİL; kullanıcı orijinal projedeki tam alan listesini
hatırlamadığı için profil serbest biçimli bir JSON `dict` olarak
saklanıyor. Şema netleştiğinde (bkz. `RoasterInterface_Fonksiyon_Referansi.md`)
UI tarafı hangi alanları göstereceğine karar verir, `ProfileStore`
değişmeden kalır. Profil adları path-traversal'a karşı regex ile
doğrulanıyor (`services/profile_store.py` içindeki `_VALID_NAME`).
`tests/test_profile_store.py` — 18 test, gerçek dosya sistemine
(`tmp_path`) karşı, hepsi geçiyor.

## UI mimarisi — netleştirilen karar (henüz uygulanmadı)

Kullanıcı, orijinal uygulamanın ana ekranının şöyle çalıştığını hatırlıyor:
sıcaklıklar/zaman/işlem durumu/grafik alanı **sabit** kalıyor, üstte
sekmeler (tab) ile Profil seçimi ve Manuel Kontrol gibi paneller bu sabit
alanın etrafında/altında değişiyordu — ayrı ayrı gezinilen tam ekranlar
değil. v2'de `HomeScreen` şu an sadece bir LED + "yakında" butonlarından
oluşan basit bir iskelet (bkz. yukarı); bu, **ProfileStore ve Live
Roast/Manual Control mantığı netleşince aynı adımda** bu sabit-alan +
sekme yapısına göre yeniden kurgulanacak (kullanıcı sırayı böyle istedi:
önce veri katmanı, sonra arayüz). Ayrı `ProfileScreen`/`LiveRoastScreen`
gibi tam ekranlar açan navigasyon fikri (ilk taslakta vardı) bu yüzden
**terk edildi**.

## Sırada ne var (henüz yazılmadı)

Kullanıcıyla üzerinde anlaşılan sıra:

1. ~~`ModbusTCPClient` + testleri~~ ✅
2. ~~Simülatöre karşı gerçek soket testi~~ ✅
3. ~~`ModbusService` (thread'li) + testleri~~ ✅
4. ~~`BaseRoasterScreen` + `HomeScreen`'i gerçek bir Kivy `App`'e bağlamak,
   LED + offline giriş doğrulaması~~ ✅ (2026-09-06, bkz. yukarıdaki not —
   davranışsal/zamanlama kanıtı tam, piksel bazlı görsel kontrol kullanıcı
   tarafından `python main.py` ile elle teyit edilmeli)
5. ~~`ProfileStore` (JSON okuma/yazma/listeleme)~~ ✅ (2026-09-06, bkz.
   yukarıdaki not — şema kasıtlı olarak serbest bırakıldı)
6. **← BURADAYIZ.** `HomeScreen`'i sabit sıcaklık/zaman/grafik alanı +
   üstte sekmeli (Profil/Manuel Kontrol) panel yapısına göre yeniden
   kurgulamak (bkz. "UI mimarisi" notu). Live Roast verisi için henüz bir
   servis yok — muhtemelen bu adımda `ModbusService` üzerinden canlı
   register aboneliği + grafik widget'ı gerekecek.
7. `config/settings.py` ile tüm register sabitlerini ve `.env` ile
   kimlik/host bilgilerini merkezileştirme (şu an `main.py` içinde sadece
   `MODBUS_HOST`/`MODBUS_PORT` ortam değişkenleri okunuyor — geçici).
8. Launcher'ın gerçek entegrasyonu ve testi.

## Dikkat edilmesi gerekenler

- Kullanıcı Türkçe konuşuyor, kod içi yorumlar Türkçe, tanımlayıcılar
  (fonksiyon/sınıf isimleri) İngilizce — bu tutarlılığı koruyun.
- Her yeni parça için **gerçek testler yazılıp çalıştırılmalı** (mock veya
  simülatöre karşı) — bu oturumda kurulan alışkanlık bu, sadece "derlendi"
  ile yetinilmiyor.
- Orijinal projedeki register haritasını (`MW580-609`, `MW700-703`, `M50-M59`
  gibi) v2'de aynen korumak gerekiyor çünkü PLC tarafı aynı — bu konuda
  ayrıntılı bir referans, önceki analiz oturumunda çıkarılan
  `RoasterInterface_Fonksiyon_Referansi.md` dosyasında mevcut (kullanıcıda
  duruyor olmalı).