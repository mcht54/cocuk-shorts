# Çocuk Shorts — otomatik üretim ve yükleme

GitHub Actions'ta günde 2 kez (08:30 ve 17:30 TR) kendiliğinden çalışır:

1. Testler koşar; geçmezse üretim yapılmaz.
2. Tür seçilir (masal / eğitici / hayvan; izlenmesi yüksek türe daha çok sıra, art arda aynı tür yok).
3. Gemini senaryo yazar → ikinci Gemini denetimi + yasaklı kelime filtresi.
4. edge-tts seslendirme (Emel), kodla üretilen telifsiz müzik.
5. Her sahne için görsel: Cloudflare FLUX → kalite kontrolü → olmazsa **yerel çizim**
   (Noto emoji figürleri + çizilmiş ortam; ana karakter tüm sahnelerde aynı).
6. Kelime vurgulu altyazılı 1080x1920 video.
7. **Yayın öncesi kalite kontrolü** (gerçek MP4 üzerinde): süre 15-59 sn ve beklenenle uyumlu,
   ses ve görüntü süreleri eşit, ses var ve kırpılmıyor, 2 sn'den uzun sessizlik yok, her sahne
   karesi gerçek çizim, sahneler donmuş değil, her kelime söylenirken altyazıda, konuşmada
   0.8 sn'den uzun altyazısız an yok. Geçmezse yeni senaryoyla 1 kez daha denenir; yine
   geçmezse **yayımlanmaz** ve çalıştırma başarısız sayılır (GitHub e-posta gönderir).
8. `YAYIN=acik` ise YouTube'a yüklenir (çocuklara yönelik + yapay zekâ beyanı), ardından
   YouTube'dan gerçek yayın durumu okunur. İstenen durum değilse (ör. denetimsiz projede
   "private" kilidi) kayıt `kilitli` olur ve sonraki çalıştırmalar yüklemeyi durdurur.
9. `gecmis.json` repoya yazılır; geçici dosyalar silinir. Yayımlanmayan video 3 gün,
   çalışma kaydı 14 gün Actions "Artifacts" altında indirilebilir.

## Ücretsiz kotalar (2026-10'da doğrulandı) ve koruma sınırları

| Servis | Ücretsiz hak | Bizim kullanım / sınır |
|---|---|---|
| Cloudflare Workers AI | 10.000 nöron/gün. Free planda aşılırsa hata verir, ücret çıkmaz. **Workers Paid planında aşım faturalanır.** | Görsel ≈ 77 nöron, video ≈ 540. Kod günlük 4.000'de durur (`CF_GUNLUK_NORON`). Kota/yetki hatasında o çalıştırmada tekrar denenmez, yerel çizime geçilir. |
| Gemini API | Proje başına, modele göre değişir; güncel sınır AI Studio > kota sayfasında. **Faturalandırma açık projede ücret çıkabilir.** | Video başına 2-8 çağrı; günlük 30 çağrıda durur (`GEMINI_GUNLUK_CAGRI`). |
| GitHub Actions (özel repo) | 2.000 dk/ay, 500 MB artifact | Çalıştırma ≈ 3-4 dk → ≈ 250 dk/ay; artifact ≈ 30 MB |
| YouTube Data API | 10.000 birim/gün | Günde 2 yükleme + birkaç okuma |

Hiçbir yerde ücretli servise otomatik geçiş yoktur.

**Bilinen risk:** edge-tts, Microsoft Edge'in "sesli oku" servisini resmî olmayan yoldan kullanır.
Ücretsizdir ama Microsoft'un garanti ettiği bir API değildir; erişim kesilirse çalıştırma hata
verir (sahte/sessiz video yayımlanmaz).

## Yerel kontrol

```
./venv/bin/python -m unittest discover -s tests            # birim testleri
ENTEGRASYON=1 ./venv/bin/python -m unittest discover -s tests  # + uçtan uca video
./venv/bin/python calistir.py --senaryo ornekler/masal.json   # anahtarsız örnek video -> cikti/
```

## Lisanslar

- Figürler: Google Noto Emoji görselleri (`assets/emoji`, Apache 2.0 / OFL 1.1 — videoda kullanım serbest)
- Yazı tipi: Baloo 2 (OFL 1.1)
- Müzik: kodla üretilir, telif yok
