# 3D Çocuk Animasyon Stüdyosu (yerel, Blender)

Mevcut 2D sistem (`calistir.py`, `cocuk/`) olduğu gibi duruyor. 3D hattı ayrı: `cocuk3d/`, `uret3d.py`,
`kuyruk.py`, `yayinla3d.py`, `seri/`. Hiçbir 3D komutu kendiliğinden yayın yapmaz.

## Kurulum

```
brew install --cask blender          # 5.2.3 LTS, ücretsiz (GPL), ≈1 GB
./venv/bin/pip install numpy         # requirements-3d.txt
```

Donanım (ölçülen): Apple M3 Pro, 18 GB bellek, Metal GPU. EEVEE ile önizleme (yarı çözünürlük, 8 örnekleme)
≈0.12 sn/kare; tam kalite süresi rapordaki `uretim_suresi_sn` alanında.
Boş disk en az 15 GB olmalı (`EN_AZ_BOS_DISK_GB`); ara PNG kareleri bölüm başına 1-3 GB, kalite geçince silinir.

## Akış

```
seri/<seri>/seri.json          karakter kimlikleri, değişmez özellikler, ses profilleri, mekânlar, nesneler
seri/<seri>/bolumler/bNNN.json çekimler: kamera tipi/hareketi, ışık, diyalog satırları, eylemler
        │  planla.py   seslendirme (önbellekli) → çekim süreleri → kare kare animasyon/kamera/ışık → ses karışımı
        ▼
uretim/<seri>/<is>/plan.json
        │  blender_sahne.py kur   rig'li karakterler + mekân + anahtar kareler → sahne.blend + meta.json
        │  blender_sahne.py render (çekim çekim, var olan kare atlanır → kaldığı yerden devam)
        ▼
        │  kurgu.py   altyazı (konuşanın rengi) + Shorts kanca başlığı + ses → MP4
        │  kalite3d.py  (aşağıda) → rapor.json
        ▼
cikti3d/<seri>/<bolum>-<profil>-<zaman>.mp4 + .rapor.json + .veri/   (animasyon_turu: 3d_blender)
   .veri/ = o videonun kendi meta/kurgu/altyazı verisi + video.sha256; kalite kontrolü veriyi
   yalnız aynı SHA'lı videoyla kabul eder (sonraki render iş klasörünü değiştirse bile)
```

Komutlar:

```
./venv/bin/python uret3d.py --bolum seri/findik-ile-pamuk/bolumler/b001.json --profil shorts --onizleme
./venv/bin/python uret3d.py --bolum ... --profil shorts                 # tam kalite
./venv/bin/python uret3d.py --bolum ... --profil uzun --prototip        # 16:9; prototip <60 sn'ye izin
./venv/bin/python uret3d.py --bolum tests/veri/test_cevrimdisi.json --seri seri/findik-ile-pamuk --profil shorts --onizleme
sandbox-exec -p '(version 1)(allow default)(deny network*)' <komut>    # ağı gerçekten kapatarak çalıştırma
./venv/bin/python kuyruk.py ekle <bolum> shorts ; kuyruk.py calistir --toplu 2 ; kuyruk.py liste
./venv/bin/python yayinla3d.py <mp4>                                     # yalnız denetler, onay kodu verir
```

## Karakterler ve devamlılık

- Karakterler koddan üretilir (`blender_sahne.karakter_kur`): 16 kemikli iskelet (gövde, baş, kollar,
  bacaklar, kuyruk, kulaklar, gözler, kaşlar, ağız). Göz kırpma, kaş/kulak/baş ile ifade
  (normal/mutlu/üzgün/şaşkın), sesin şiddetinden ağız hareketi, nefes ve kuyruk sallama.
- Eylemler: yürü, koş, zıpla, otur, kalk, el salla, nesne tut, nesne ver, bak, ifade.
- Her karakterin model parmak izi `seri/<seri>/karakter_izleri.json`'a ilk geçen bölümde yazılır;
  sonraki bölümlerde farklı model çıkarsa kalite kontrolü reddeder. Yeni karakter yalnız `seri.json`'a
  eklenerek gelir; bölüm dosyası tanımsız karakter kullanırsa planlama durur.
- Bölüm dosyası `onceki_olaylar` / `bu_bolumde_degisen` alanlarıyla hikâye devamlılığını taşır.

## Profiller

| | Shorts | Uzun |
|---|---|---|
| Kadraj | 1080×1920 (9:16) | 1920×1080 (16:9) |
| Süre | 15-59 sn | 60-1800 sn (`--prototip` ile 20 sn'den) |
| Açılış | ilk 2.5 sn ekranda kanca başlık | anlatıcının seri+bölüm adını söylediği açılış çekimi |
| Yerleşim | yatay mesafeler ×0.75, kamera uzaklığı dikey görüş açısına göre | olduğu gibi |

## Kalite kontrolü (`kalite3d.py`) — geçmeyen video yayın kuyruğuna giremez

Dosya: yönelim/en-boy, görüntü süresi = kare/fps, ses ve görüntü süreleri eşit, profil süre aralığı.
Ses: ortalama > -35 dB, kırpılma yok, 2 sn'den uzun boşluk yok, **konuşma müziğin ≥10 dB üstünde**.
Altyazı: söylenen her kelime ekranda, satır içinde ≤0.8 sn boşluk.
Görüntü (bitmiş MP4 kare kare): siyah kare yok, >1 sn donuk görüntü yok, boş kare yok, eksik kare yok.
Poz: el sallama/zıplamada kalkan el gövdenin dışında (≥0.32 m yana; kolları gövdeye gömen hatalı
rig 0.05/0.24 m ölçtü), zıplamada ≥0.15 m yükselme; ağız dikey ölçeği ≤3.2× (hatalı sürüm 7.9× idi).
Animasyon (Blender ölçümü): hedef karakter kadrajda (yakın çekimde yüz, diğerlerinde 6 noktadan ≥5),
yürüme çekiminde ≥0.25 m yer değiştirme, eylemli çekimde uzuv hareketi, hareketli kamerada kamera yolu,
ışık geçişinde güneş değişimi, çekim geçişlerinde açı değişimi.
Senkron: bitmiş MP4'ün sesinden çıkarılan zarf ile ağız hareketinin korelasyonu ≥0.5
(ölçülen: kaymasız 0.79/0.85; 1 kare (42 ms) kayma geçer, ≥84 ms kayma reddedilir).
Devamlılık: karakter parmak izi seri kaydıyla aynı.

## YouTube

- Varsayılan: yükleme yok. `yayinla3d.py` video başına onay kodu ister, yalnız kalite geçmiş tam
  kalite videoyu, yalnız `private` yükler; aynı dosya/bölüm-profil ikinci kez yüklenmez (`yayin_kaydi.json`).
- `unlisted`/`public` ayrıca `--herkese-acik-onay HERKESE-ACIK-<kod>` ister. Zamanlanmış yayın yok.
- OAuth asgari yetki: `youtube.upload` (istatistik için `yetki_al.py --istatistik` ile salt okuma).
  Sırlar yalnız ortam değişkeninde/GitHub Secrets'ta; `.env`, `client_secret*.json` git'e girmez.
- Hedef kitle: içerik 3-7 yaş için tasarlandığından `selfDeclaredMadeForKids: true` (doğru beyan).
  3D Blender çizgi filmi gerçekçi sentetik içerik olmadığından `containsSyntheticMedia: false`
  (seslendirme sentetik ama gerçek bir kişiyi taklit etmiyor) — farklı karar istenirse değiştirilir.
- Denetimsiz API projesinin yüklemeleri YouTube tarafından private kilitlenir; bu aşılmaya çalışılmaz.

## Doğrulama geçmişi (2026-10-26)

Elle kare incelemesi iki gerçek kusur buldu; ikisini de otomatik kontrol ilk başta kaçırmıştı:
1. Zıplama/el sallamada kollar gövdenin içine dönüyordu (kemik dönüş işareti ters) → düzeltildi,
   yana açılma kontrolü eklendi.
2. Şaşkın/sevinçli konuşmada ağız 7.9× uzayıp "sarkan dil" gibi görünüyordu → 2.8× üst sınır,
   ağız kontrolü eklendi. Yatay yakın çekim başı kesiyordu → baş+omuz kadrajı.
Ayrıca parmak izi nesne adlarına bağlıydı (.001 ekleri) → parça adları karakter kimliğiyle başlar;
eski kayıt geçersiz sayıldı, seri kaydı yeni yöntemle yeniden oluşturuldu.
Bu kusurlu sürümlerin raporları `kalite_gecti: false` olarak güncellendi; videolar silinmedi.

## Bilinen kısıtlar

- **Seslendirme (edge-tts) güvenilir değil:** Ahmet sesi aralıklı "ses yok" döndü (6 denemede başarısız
  olduğu çalıştırma oldu). Microsoft'un resmî olmayan servisi; ticari kullanım hizmet şartlarına aykırı
  olabilir. Yerel, lisansı açık bir Türkçe TTS'e geçiş sonraki aşama.
- Karakterler sade, yuvarlak oyuncak tarzı; parmak, kumaş, saç simülasyonu yok. Ağız hareketi ses
  şiddetinden (fonem bazlı değil).
- Mekânlar: orman ve oda. Deniz, okul vb. henüz yok.
- Yapay zekâ video motoru (ComfyUI/Wan) kurulmadı: 18 GB bellekte nicemlenmiş model + düşük çözünürlük
  gerekir, ≈18 GB model indirmesi, karakter tutarlılığı garanti değil. Ayrı onayla değerlendirilecek.
- Uzun profil prototipi 42 sn; gerçek uzun bölüm (≥60 sn, birkaç dakika) henüz üretilmedi.
- Kalite kontrolü baş tepesi/kulak kırpılmasını ölçmüyor (iki kişilik çekimde kulak uçları kadraj
  kenarına değiyor); kompozisyon kalitesi hâlâ elle incelenmeli.
- Zamanlayıcı yalnız Mac açıkken çalışır. `kuyruk.py plan-dosyasi` launchd dosyasını üretir ama yüklemez.
- Ücretsiz servislerin sınırsız olmadığı: Cloudflare günde 10.000 nöron (kod 4.000'de durur), Gemini
  proje kotası, YouTube API günlük 10.000 birim, GitHub Actions özel repoda 2.000 dk/ay.
