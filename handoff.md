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

### `config/settings.py`
**2026-09-07 oturumunda yazıldı.** Madde 7'nin bir kısmı erkenden yapıldı
çünkü `HomeScreen`'in canlı sıcaklıkları göstermesi için gerekliydi. PLC
host/port/unit_id/timeout ve sıcaklık register'ları (`REG_SET_TEMP=2020`,
`REG_BEAN_TEMP=2021`, `REG_EXHAUST_TEMP=2022`) burada toplu. **Bu
register adresleri YER TUTUCU** — `tools/modbus_simulator.py` ile aynı
ama gerçek PLC'nin register haritası muhtemelen farklı (bkz. aşağıdaki
"Dikkat edilmesi gerekenler": MW580-609 aralığı). Kullanıcı şu an gerçek
adresleri hatırlamıyor/elinde değil; `RoasterInterface_Fonksiyon_Referansi.md`
bulununca sadece bu dosyadaki sabitler güncellenecek, başka hiçbir yer
değişmeyecek. `.env` entegrasyonu henüz yok, sadece `os.environ.get` ile
ortam değişkeni okunuyor.

### `widgets/temp_graph.py`
Bağımlılıksız (kivy_garden gerektirmeyen), son N örneği canvas Line ile
çizen basit kayan grafik. Eksen etiketi/skala çizgisi yok — henüz
istenmedi.

## UI mimarisi — uygulandı (2026-09-07)

Kullanıcı, orijinal uygulamanın ana ekranının şöyle çalıştığını hatırladı:
sıcaklıklar/zaman/işlem durumu/grafik alanı **sabit** kalıyor, üstte
sekmeler (tab) ile Profil seçimi ve Manuel Kontrol gibi paneller bu sabit
alanın altında değişiyordu — ayrı ayrı gezinilen tam ekranlar değil. Ayrı
`ProfileScreen`/`LiveRoastScreen` gibi tam ekranlar açan navigasyon fikri
(ilk taslakta vardı) bu yüzden **terk edildi**.

`HomeScreen` bu yapıya göre yeniden kuruldu:
- Sabit üst alan: bağlantı LED'i, Set/Bean/Egzoz sıcaklık etiketleri
  (`ModbusService.subscribe("home_live_temps", ...)` ile abone olunuyor,
  `on_enter`'da abone olunuyor/`on_leave`'de `unsubscribe` ediliyor),
  `TempGraph` widget'ı (bean temp'i çiziyor).
- Alt kısım: `TabbedPanel` — "Profil" sekmesi `ProfileStore.list_profiles()`'ı
  listeliyor, bir profile dokununca şimdilik sadece içeriğini toast olarak
  gösteriyor (PLC'ye gerçekten uygulama mantığı henüz yok — bu, muhtemelen
  bir "kavurmayı başlat" akışıyla birlikte gelecek). "Manuel Kontrol"
  sekmesi şimdilik yer tutucu metin — hangi register/coil'lerin
  yazılacağı bilinmiyor.
- **Bilinçli olarak eklenmedi:** kronometre (süre) ve süreç aşaması
  (kurutma/sararma/ilk çatlak vb.) göstergeleri — kullanıcı bunların hangi
  coil/register'a bağlı olduğunu hatırlamıyor, sahte/işlevsiz bir şey
  koymak yerine register haritası netleşene kadar bekletildi.

**Davranışsal olarak doğrulandı** (gerçek pencere, simülatöre karşı):
`plc_connected=True`, sıcaklıklar doğru ölçeklenip (`/10`) gösteriliyor,
6 saniyede grafik 20 nokta biriktirdi, profil listesi `ProfileStore`'dan
doğru okunuyor. Piksel bazlı görsel kontrol yine kullanıcı tarafından
`python main.py` ile yapılmalı (bkz. yukarıdaki ekran görüntüsü notu).

## Orijinal ana ekranın gerçek yapısı (2026-09-07, kullanıcı ekran görüntüsü paylaştı)

Kullanıcı orijinal uygulamadan bir ekran görüntüsü paylaştı. Bu, tahmin
ettiğimizden daha zengin bir yapı — v2'nin `HomeScreen`'i şu an bunun çok
sadeleştirilmiş bir hâli, aşağıdaki eksikler bilerek not ediliyor.

**Üst sekmeler (4 tane, 2 değil):** Home, Manuel Control, Make Profile,
Profile. v2'de şu an sadece Profil + Manuel Kontrol var — **Make Profile**
(profil oluşturma/düzenleme) ayrı bir sekme olarak eksik, "Profile"
sekmesi muhtemelen sadece var olanları seçmek/uygulamak için.

**Sol panel (sabit, tüm sekmelerde aynı kalıyor gibi görünüyor):**
- Set Value, Bean Temp, Exhaust TEMP (v2'de zaten var)
- **3 yarım-daire gösterge (yeni, v2'de yok):** Exhaust (%), Burner (%),
  Airflow (Pa) — bunlar hangi register'dan geliyor bilinmiyor, register
  haritası ile birlikte gelecek.

**Sağ panel (sabit, v2'de tamamen eksik):**
- Roasting Time (toplam süre, 00:00 formatı)
- Drying Time / Maillard Time / Development Time — her biri süre +
  yüzde (muhtemelen toplam sürenin yüzdesi olarak faz payı)
- Rate Of Rise (RoR): anlık °C ve "°C max" — bean temp'in türevi
  (dakikadaki artış), muhtemelen **hesaplanabilir** (register'a ihtiyaç
  yok, bean temp geçmişinden hesaplanır) — bu register haritası
  beklemeden şimdi bile eklenebilir.
- Sağ altta bir saat/durum göstergesi (yeşil, "21:11:07") — muhtemelen
  sistem saati, PLC'den gelmiyor olabilir.
- **"Profile Start" butonu** — kavurmayı başlatan gerçek tetik. Hangi
  coil'e yazdığı register haritasıyla netleşecek.

**Orta alan ("Make Profile" sekmesi aktifken):**
- Canlı grafik: X ekseni 0-20 dakika, Y ekseni 0-300°C, 4 seri: SET
  (kırmızı), BT/Bean Temp (mavi), EXH/Exhaust (sarı), ROR x5 (yeşil,
  RoR'un 5 katı ölçekle çizilmiş hali — okunabilirlik için). v2'deki
  `TempGraph` şu an sadece tek seri (bean temp) çiziyor, bu 4 seriye
  genişletilmeli.
- "Machine Ready" durum metni (makine boştayken)
- **Profil tablosu — bu, `ProfileStore`'un sakladığı asıl şemayı netleştiriyor:**
  satırlar: Drop Down Temp, Hopper Open Time, Chaffing (sec), Chaffing
  Time (sec), First Crack Temp, Second Crack Temp, DROP OUT TEMP. Her
  satırın üç sütunu var: Temperature/Time (ana değer), Exhaust (%),
  Flame (%) — yani her aşamanın kendi hedef sıcaklığı/süresi VE o
  aşamadaki egzoz/alev yüzdesi ayrı ayrı tanımlanabiliyor. Muhtemel JSON
  şeması:
  ```json
  {
    "drop_down_temp": {"value": 0.0, "exhaust_pct": 0, "flame_pct": 0},
    "hopper_open_time_sec": {"value": 0, "exhaust_pct": 0, "flame_pct": 0},
    "chaffing_sec": {"value": 0, "exhaust_pct": 0, "flame_pct": 0},
    "chaffing_time_sec": {"value": 0, "exhaust_pct": 0, "flame_pct": 0},
    "first_crack_temp": {"value": 0.0, "exhaust_pct": 0, "flame_pct": 0},
    "second_crack_temp": {"value": 0.0, "exhaust_pct": 0, "flame_pct": 0},
    "drop_out_temp": {"value": 0.0, "exhaust_pct": 0, "flame_pct": 0}
  }
  ```
  **Kullanıcı bu şemayı onayladı (2026-09-07).** `screens/home_screen.py`
  içindeki `PROFILE_FIELDS` sabiti bu 7 satırı ve alan adlarını tanımlıyor.
  `ProfileStore` zaten şemadan bağımsız (serbest dict) olduğu için bu
  şema netleşince sadece UI tarafı (Make Profile ekranı) değişecek,
  `ProfileStore`'un kendisi DEĞİŞMEYECEK.

**Sonuç:** "zaman" ve "processler" dediği şey tam olarak bu sağ paneldeki
Drying/Maillard/Development süreleri + yüzdeleri imiş. Bunlardan
Roasting Time ve Rate Of Rise register'a ihtiyaç duymuyor — **aşağıda
uygulandı**. Drying/Maillard/Development fazlarının SINIRLARI (hangi
sıcaklıkta bir fazdan diğerine geçildiği) hâlâ belirsiz ve
UYGULANMADI — muhtemelen aktif profildeki eşiklerden (first_crack_temp
vb.) türetilebilir ama bu kesinleşmedi, tahmin etmek yerine bekletildi.

## Modern görsel yenileme + RoastSession (2026-09-07)

Kullanıcı, mevcut tasarımın (paylaşılan ekran görüntüsü) görsel olarak
demode göründüğünü belirtti. Karar: **bilgi mimarisini** (sabit sol/sağ
panel + değişen orta alan) korumak ama görsel dili tazelemek — komple
farklı bir yaklaşıma geçmedik.

### `services/roast_session.py`
Register'dan tamamen bağımsız: `start()`/`stop()` ile "Profile Start"
butonuna bağlı, `feed_sample(bean_temp)` ile beslenen bir pencereden
(`ror_window`, varsayılan 60s) Rate of Rise (°C/dakika) ve elapsed time
hesaplıyor. `tests/test_roast_session.py` — 12 test, sahte (enjekte
edilebilir) saatle, gerçek zaman beklemeden çalışıyor, hepsi geçiyor.

### `widgets/multi_temp_graph.py`
Eski tek-serili `widgets/temp_graph.py`'nin yerini aldı (o dosya
silindi). SET/BT/EXH/ROR olmak üzere 4 seriyi aynı eksende çiziyor;
"hero" olarak işaretlenen seri (BT) altında yarı saydam bir dolgu var
(`Mesh` + `triangle_strip` — dalgalı eğrilerde `triangle_fan`'ın
üreteceği kendini-kesen üçgen sorununu önlemek için özellikle
`triangle_strip` seçildi).

### `screens/home_screen.py` — tamamen yeniden yazıldı
- Sol panel: LED + Set/Egzoz (26sp) + **Bean Temp "hero" rakam (44sp)**.
- Orta: `MultiTempGraph` + 3 sekmeli `TabbedPanel` (Profil / Manuel
  Kontrol / **Make Profile** — bu üçüncü sekme yeni).
- Sağ panel: Roasting Time, Rate Of Rise (+ max), **"Profile Start" /
  "Durdur" butonu** — `RoastSession`'ı gerçekten başlatıp durduruyor.
- **Make Profile sekmesi (yeni):** `PROFILE_FIELDS`'a göre 7 satır × 3
  sütun (Değer/Exhaust%/Alev%) `TextInput` formu + profil adı + "Profili
  Kaydet" butonu → `ProfileStore.save_profile()`. Sayısal doğrulama var
  (geçersiz girişte toast ile hata, kaydetmiyor).
- Tüm panel/grafik arka planları `RoundedRectangle` ile yuvarlatılmış
  kart görünümünde (`<Card@BoxLayout>` KV kuralı).

**Davranışsal olarak doğrulandı** (gerçek pencere, simülatöre karşı):
kavurma başlatıldıktan ~4.5s sonra `roasting_time=00:04`,
`ror=5.7 °C/dk` (`max=6.6`), 4 serinin hepsi grafik noktası biriktiriyor,
Make Profile formundan kaydedilen profil (`first_crack_temp`: value=205,
exhaust_pct=60, flame_pct=40) `ProfileStore`'dan doğru şemayla geri
okundu ve Profil sekmesinde listelendi.

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
6. ~~`HomeScreen`'i sabit sıcaklık/grafik alanı + sekmeli (Profil/Manuel
   Kontrol) panel yapısına göre yeniden kurgulamak~~ ✅ (2026-09-07, bkz.
   "UI mimarisi — uygulandı" notu)
7. ~~`HomeScreen`'i modern görsel dille + `RoastSession` (Roasting
   Time/RoR) ile güçlendirmek, Make Profile sekmesi~~ ✅ (2026-09-07,
   bkz. "Modern görsel yenileme" notu)
8. **← BURADAYIZ / BEKLEMEDE.** Aşağıdakilerin hepsi gerçek register
   haritasına (`RoasterInterface_Fonksiyon_Referansi.md`) bağımlı,
   kullanıcı henüz bulamadı:
   - `config/settings.py`'deki yer tutucu register adreslerini
     gerçekleriyle değiştirmek
   - "Manuel Kontrol" sekmesine gerçek yazma butonları eklemek
   - Drying/Maillard/Development faz sınırlarını belirlemek (hangi
     sıcaklık/coil'de bir fazdan diğerine geçildiği)
   - Exhaust/Burner/Airflow gösterge (%) değerlerini gerçek register'a
     bağlamak
   - "Profile Start" butonunun PLC'ye gerçekten bir coil yazması (şu an
     sadece yerel `RoastSession`'ı tetikliyor, PLC'yi başlatmıyor)
   - `.env` entegrasyonu (host/port hâlâ sadece ortam değişkeni)
9. ~~Launcher'ın gerçek entegrasyonu ve testi~~ ✅ (2026-09-07, bkz.
   "Launcher yeniden yazıldı" notu — sadece gerçek üretim sunucusu
   entegrasyonu kapsam dışı, çünkü kullanıcıda henüz yok)

**Kalan her şey register haritasına, gerçek güncelleme sunucusuna, veya
ekran/donanım bilgisine bağımlı** — hepsi kullanıcıdan bekleniyor (bkz.
bu handoff'un en altındaki "Kullanıcıdan beklenen bilgiler" listesi).

## Launcher yeniden yazıldı (2026-09-07)

`launcher.py` artık bir **iskelet değil** — `ModbusTCPClient`/`ProfileStore`
ile aynı kalıba taşındı: `Launcher` sınıfı, config `__init__`'te
(`app_dir`, `manifest_url`, `backup_dir`, `temp_zip`, `timeout`), I/O
metotları `(sonuç, hata)` tuple'ı döner.

**Güvenlik düzeltmesi:** eski kod `zipfile.extractall()`'ı doğrudan
çağırıyordu — kötü/bozuk bir zip `../../` gibi bir girişle `app_dir`
dışına yazabilirdi (zip-slip). `apply_update()` artık her zip girişinin
çözümlenmiş yolunun `app_dir` içinde kaldığını extract etmeden önce
doğruluyor, değilse `(False, "Güvensiz zip girişi...")` dönüp hiçbir şey
açmıyor.

`tools/update_server_simulator.py` (yeni) — `modbus_simulator.py` ile
aynı ruhta, sadece `http.server` kullanan minik bir sahte güncelleme
sunucusu (`version.json` + `.zip` serve ediyor). `tests/test_launcher.py`
— 21 test, bu sahte sunucuya karşı **gerçek** HTTP istekleri/indirmeler
yapıyor (mock değil), artı zip-slip reddi, rollback, checksum uyuşmazlığı
senaryoları. Tek mock edilen yer `launch_main_app` (`subprocess.Popen`)
— bu makinede gerçek bir `main.exe` yok.

`run()` metodu artık `sys.exit()` çağırmıyor (eski `main()` çağırıyordu)
— böylece testler doğrudan çağırabiliyor. `sys.exit(0)`, `if __name__ ==
"__main__":` bloğuna taşındı.

**Kapsam dışı bırakılan (gerçek sunucu gerektiriyor):** gerçek güncelleme
sunucusunun kurulması, `main.exe`'nin PyInstaller ile `onedir`
paketlenip launcher'la uçtan uca denenmesi, `launcher.spec`. Kullanıcı
gerçek sunucu bilgisini verdiğinde sadece `config/settings.py`'deki
`LAUNCHER_MANIFEST_URL` değişecek.

**Bug düzeltmesi (aynı gün, kullanıcı elle çalıştırınca yakaladı):**
`run()`, `launch_main_app()` başarısız olunca `rollback()` sonrası
**yedekten tekrar dener** — ama bu ikinci deneme `try/except` içinde
DEĞİLDİ (orijinal iskelette de aynı hata vardı, ben de fark etmeden
taşımışım). Bu geliştirme ortamında `app/main.exe` henüz yok (proje
paketlenmedi) olduğu için ikinci deneme de gerçekten başarısız oluyor ve
programı unhandled exception ile çökertiyordu — `python launcher.py`
çalıştırıldığında bunu üretti. İkinci deneme de artık `try/except`
içinde: başarısız olursa sadece hata basıp temiz çıkıyor.
`tests/test_run_does_not_crash_when_main_app_missing_both_attempts` bu
senaryoyu regresyon olarak kilitliyor.

## Launcher görsel giriş ekranı (2026-09-08)

Kullanıcı launcher'ın konsol yerine görsel bir "sürüm kontrol
ediliyor / indiriliyor / başlatılıyor" ekranı göstermesini istedi.

**`launcher.py` (`Launcher` sınıfı) genişletildi, hâlâ `kivy` import
ETMİYOR** (bilinçli — saf mantık burada kalıyor, GUI ayrı dosyada):
- `download_update(url, on_progress=None)` — `on_progress(indirilen,
  toplam)` her chunk'ta çağrılır (`Content-Length` header'ından).
- `run(on_status=None, on_progress=None) -> bool` — artık `None` yerine
  `bool` dönüyor (`True`=başlatıldı, `False`=hiç başlatılamadı). Her
  aşama geçişinde `on_status(mesaj)` çağırıyor ("Sürüm kontrol
  ediliyor...", "Güncelleme indiriliyor...", "Checksum doğrulanıyor...",
  "Başlatılıyor...", hata mesajları).
- Bu, geriye dönük uyumlu değil — `run()`'ı çağıran her yer (`__main__`
  bloğu, testler) dönüş değerini artık kullanabilir/kullanmalı.

**`launcher_app.py` (yeni)** — `main.py`/`HomeScreen` ile aynı görsel dil
(koyu tema, aynı accent renkleri). `LauncherApp`/`LauncherScreen`:
uygulama adı, durum metni, `ProgressBar` (sadece indirirken görünür),
yerel sürüm metni, hata durumunda kırmızı hata metni + "Kapat" butonu
(pencere sessizce kapanmıyor, kullanıcıya ne olduğunu gösteriyor).
`Launcher.run()` arka plan thread'inde çalışıyor,
`on_status`/`on_progress` her biri `Clock.schedule_once` ile ana thread'e
devrediyor — projenin "Kivy widget'larına sadece ana thread'den
dokunulur" kuralı burada da korunuyor (bkz. `ModbusService`/`HomeScreen`
ile aynı desen).

**`launcher.py`'nin `__main__` bloğu artık "headless yedek"** olarak
işaretlendi (GUI'siz debug/CI için) — asıl PyInstaller hedefi ve
masaüstü kısayolu `launcher_app.py`'yi hedeflemeli.

**Davranışsal olarak doğrulandı** (gerçek pencere, yerel
`update_server_simulator`'a karşı, 3 senaryo):
1. Güncelleme var → indirme gerçekleşti, `progress_value` %100'e ulaştı.
   Ardından "yeni" main.exe de gerçek bir çalıştırılabilir olmadığı için
   (test senaryosu kasıtlı) başlatma başarısız oldu → `rollback()`
   sürümü 1.0.0'a geri aldı, ekran net bir hata gösterdi (çökme yok) —
   bu, "başarılı indirilen ama çalışmayan güncellemeyi kalıcı sayma"
   davranışının **doğru** çalıştığının kanıtı.
2. Güncelleme yok + `launch_main_app` mock'landı (gerçek `.exe` yok) →
   `status_text="Başlatıldı"`, `has_error=False`, pencere kendiliğinden
   kapandı.
3. Manifest sunucusuna hiç ulaşılamıyor → çökmeden devam etti, yine
   başlatmayı denedi (mock olmadığı için beklendiği gibi başarısız oldu,
   temiz hata ekranı gösterdi).

**Kapsam dışı:** gerçek logo/ikon, borderless/frameless pencere,
`launcher.spec`/PyInstaller paketleme — hâlâ bekliyor.

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

## Kullanıcıdan beklenen bilgiler

İlerlemeyi doğrudan engelleyen açık sorular:

1. **`RoasterInterface_Fonksiyon_Referansi.md`** — gerçek register/coil
   haritası (sıcaklıklar, start/stop coil'i, süreç aşaması coil'leri,
   manuel kontrol register'ları).
2. **Gerçek güncelleme sunucusu** — manifest URL, sertifika vb. (2026-09-07
   itibarıyla "henüz yok" onaylandı).
3. **MQTT** — orijinal projede kimlik bilgileri koda gömülüydü
   (`.env`'e taşınacaktı) ama v2 planında MQTT hiç yok. Ne için
   kullanılıyordu, v2'de gerekli mi?
4. **Ekran/donanım bilgisi** — gerçek HMI panelinin çözünürlüğü/boyutu.

Orta öncelik / senin kararına bağlı:
- Drying/Maillard/Development faz sınırlarının nasıl belirleneceği
  (muhtemelen aktif profildeki eşiklerden türetilecek, ama onaylanmadı).