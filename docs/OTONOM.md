# Otonom döngü: Minik Masal Evi + Merak Arşivi

Her şey GitHub Actions'ta çalışır, bilgisayarın açık olması gerekmez. Ücretli servis yoktur.

## Takvim (Türkiye saati)

| Ne | Ne zaman | İş akışı |
|---|---|---|
| Stok doldurma (iki kanal, Gemini) | her gece 03:30 | `stok.yml` |
| Sağlık denetimi + nabız | her gün 09:00 | `saglik.yml` |
| Minik Masal Evi Shorts | her gün 17:00 | `gunluk3d.yml` |
| Minik Masal Evi uzun derleme | pazar 10:00 | `haftalik-uzun.yml` |
| Merak Arşivi uzun belgesel | salı ve cuma 18:00 | `merak.yml` |
| Merak Arşivi Shorts | her gün 19:00 | `merak.yml` |

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
