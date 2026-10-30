# Otonom döngü: Minik Masal Evi + Merak Arşivi

Her şey GitHub Actions'ta çalışır, bilgisayarın açık olması gerekmez. Ücretli servis yoktur.

## Takvim (Türkiye saati) ve haftalık onay

Videolar **1 hafta önceden** üretilip YouTube'a **zamanlanmış** yüklenir (`otonom/takvim.py`).
Her pazar 09:00 "Haftalık onay" e-postası gelir: önümüzdeki haftanın videoları, izle/Studio bağlantılarıyla.
Beğenmediğinizi YouTube Studio'da silin ya da Gizli yapın; dokunmadığınız saatinde yayınlanır (sistem durmaz).

| Yayın | Ne zaman |
|---|---|
| Minik Masal Evi Shorts | her gün 17:00 |
| Minik Masal Evi uzun derleme | pazar 10:00 (yalnız yayınlanmış Shorts'lardan, hemen yayınlanır) |
| Merak Arşivi belgesel | salı ve cuma 18:00 |
| Merak Arşivi Shorts | pazartesi, çarşamba, perşembe, cumartesi 19:00 |

| İş | Ne zaman | İş akışı |
|---|---|---|
| Stok doldurma (Gemini) | her gece 03:30 | `stok.yml` |
| Masal üretim + zamanlama | 05:00 ve 16:00 | `gunluk3d.yml` |
| Merak üretim + zamanlama | 13:00 | `merak.yml` |
| Sağlık denetimi + nabız | 09:00 | `saglik.yml` |
| Haftalık onay listesi | pazar 09:00 | `haftalik-onay.yml` |

## Özgünlük (YouTube "özgün olmayan içerik" kuralına karşı)

- Merak: her belgeselde en az 6, her Shorts'ta en az 1 kodla çizilmiş özgün grafik (harita, zaman
  çizelgesi, sayaç, karşılaştırma); 5 farklı anlatım tarzı dönüşümlü.
- Masal: özgün karakterler; 7 mekân (kış Ara-Şub, sahil Haz-Eyl), 6 nesne; çoğu bölüm macera.

## İçerik nereden gelir

- **Minik Masal Evi:** `otonom/masal_yaz.py` Gemini ile yeni bölüm yazar (çoğu macera/aksiyon), bölüm
  `cocuk3d/bolum_denetle.py` ve çocuk güvenliği denetiminden geçmezse hatalarla düzelttirilir, yine
  geçmezse yazılmaz. Hedef stok 21 bölüm.
- **Merak Arşivi:** `merak/konu.py` Gemini'den konu adayı alır; Wikipedia makalesi, metin uzunluğu,
  serbest lisanslı görsel sayısı ve okunma sayısıyla doğrular. `merak/yaz.py` yalnız Wikipedia metninden
  1 uzun + 4 Shorts senaryosu yazar. Yanlış bilgiye karşı: kaynakta geçmeyen sayı kodla reddedilir,
  her iddianın kaynaktan birebir alıntısı aranır, ayrı bir Gemini çağrısı cümle cümle denetler.
  Görseller yalnız CC BY / CC BY-SA / CC0 / kamu malı; her karede yazar + lisans görünür,
  tam liste `merak/konular/<konu>/KAYNAKLAR.md`.

Her video yayından önce kalite kontrolünden geçer (süre, çözünürlük, siyah/donuk kare, ses).
Geçmeyen yayımlanmaz, aynı gün sıradaki denenir; iki kez kalan atlanır.

## Anahtarlar ve ayarlar (GitHub → Settings → Secrets and variables → Actions)

Secrets: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` (Minik Masal Evi),
`MERAK_YT_REFRESH_TOKEN` (Merak Arşivi), `GEMINI_API_KEY`.

Variables: `YAYIN` / `MERAK_YAYIN` (`acik` = yükle), `YT_GIZLILIK`, `UZUN_GIZLILIK`, `MERAK_GIZLILIK`
(`public`), `YT_HERKESE_ACIK_ONAY=evet`, `MERAK_BASLANGIC` / `DERLEME_BASLANGIC` (sağlık denetimi bu
tarihten sonra o hattı bekler).

## Bir şey bozulursa

Sağlık denetimi sorun bulursa depoda **"Otomasyon uyarısı"** issue'su açılır ve GitHub e-posta gönderir.
Sık sebepler ve çözümleri:

- **YouTube yetkisi geçersiz** (Google şifresi değişti, izin kaldırıldı): bilgisayarda
  `python yetki_al.py client_secret_findik.json` → doğru kanalı seç → çıkan refresh token'ı ilgili
  secret'a yaz (`gh secret set YT_REFRESH_TOKEN` ya da `MERAK_YT_REFRESH_TOKEN`).
- **Gemini anahtarı/kotası**: aistudio.google.com'dan yeni anahtar → `gh secret set GEMINI_API_KEY`.
  Stok ~3 hafta olduğu için birkaç günlük kesinti yayını durdurmaz.
- **Seslendirme (edge-tts) bozuldu**: Microsoft'un resmî olmayan servisidir; kütüphane her kurulumda en
  yeni sürüme güncellenir, çoğu kırılma kendiliğinden düzelir.
- **Bir iş akışı kapandı**: Actions sekmesinde iş akışını seçip "Enable workflow".

Depo her gün nabız commit'i aldığı için GitHub zamanlanmış işleri hareketsizlik yüzünden kapatmaz.
