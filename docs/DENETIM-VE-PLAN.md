# Denetim raporu ve 3D geçiş planı (2026-10-26)

## 1. Mevcut sistem (değiştirilmeden önce)

| Bileşen | Durum |
|---|---|
| Dil/ortam | Python 3.14.8 (`venv`), edge-tts 7.3.1, Pillow 13.0.0, requests 2.34.2; ffmpeg (Homebrew, libx264 + VideoToolbox, **libass/drawtext yok**) |
| Video motoru | `cocuk/video.py`: sahne başına **tek sabit görsel** + PIL ile kare kare yakınlaştırma/kaydırma (Ken Burns), 0.3 sn çapraz geçiş, kelime vurgulu altyazı, ffmpeg'e ham kare akışı |
| Görsel | `cocuk/gorsel.py`: Cloudflare FLUX (anahtar yok → hiç çalışmadı) → isteğe bağlı Pollinations (kapalı) → `cocuk/cizim.py` yerel çizim (PIL ortam + Noto emoji figürleri) |
| Ses | edge-tts (Microsoft Edge "sesli oku" servisi, tek anlatıcı Emel), kodla üretilen müzik kutusu müziği, tepe sınırlayıcı |
| Kalite | `cocuk/kalite.py`: süre, akışlar, ses seviyesi/sessizlik/kırpılma, altyazı kapsamı, sahne karelerinde boş/donmuş görüntü |
| Senaryo/yayın | `senaryo.py` Gemini (anahtar yok → hiç çalışmadı), `youtube.py` (hiç çalışmadı), GitHub Actions iş akışı (repo yok) |
| Testler | 23 test; 22 geçiyor + 1 uçtan uca (ENTEGRASYON=1 ile ayrıca geçti) |

**Üç örnek video nasıl üretildi:** `calistir.py --senaryo ornekler/*.json`, anahtarsız → her sahne yerel
çizim (`gorsel_kaynaklari: yerel` ×7). **Hiçbiri animasyon değil:** her sahne tek sabit resim; hareket
yalnız resmin yakınlaştırılması/kaydırılması ve sahneler arası geçişten ibaret. Karakterler hareket etmez,
uzuv/ifade/dudak hareketi yoktur. Bu videolar "2D hareketlendirilmiş görsel" olarak sınıflandırılır,
**3D animasyon olarak işaretlenmeyecek.**

## 2. Donanım (ölçüldü)

- Apple M3 Pro, 12 CPU çekirdeği, 18 çekirdek GPU (Metal 4), **18 GB birleşik bellek**
- Disk: 926 GB, **213 GB boş** (%77 dolu)
- Blender: kurulu değil (Homebrew'da 5.2.3 mevcut, ücretsiz, GPL)
- ComfyUI: kurulu değil

## 3. Doğrulanan dış kısıtlar

- **edge-tts:** Kod GPL-3; ama Microsoft'un servisini resmî olmayan yoldan kullanır. Microsoft Q&A'da bir
  moderatör, Azure aboneliği olmadan ticari kullanımın hizmet şartlarını ihlal edebileceğini söylüyor.
  Para kazanan kanalda **hukuki/erişim riski** var. Plan: yerel, lisansı açık Türkçe TTS seçeneğini
  ayrı motor olarak eklemek (aşama 6); seçim kullanıcıda.
- **Yapay zekâ video (Wan 2.2 5B vb.):** M3 için ölçüm yok; 64 GB Mac'lerde rahat, 18 GB'ta nicemlenmiş
  model + düşük çözünürlük gerekir; model dosyaları ≈ 18 GB. Karakter tutarlılığı bölümler arası
  garanti değil. **Şimdilik kurulmayacak**; ayrı motor arayüzü + durum raporu hazırlanacak.
- **YouTube:** Denetimsiz API projesinin yüklemeleri kalıcı "private" kilitlenir. İlk aşamada
  herkese açık yayın kapalı; yükleme yalnız açık `private` ve video başına ayrı onayla.

## 4. Neden Blender

Ücretsiz/yerel, Python ile tamamen komut satırından sürülebilir (`blender -b -P betik.py`), Metal ile
GPU hızlandırmalı EEVEE/Cycles, gerçek iskelet (armature) + şekil anahtarı (shape key) ile rig, kamera ve
ışık animasyonu. Karakterler kodla üretilir → her bölümde birebir aynı model (tutarlılık garantisi),
dışarıdan telifli model gerekmez.

## 5. Aşamalı plan

| Aşama | İçerik | Kabul ölçütü |
|---|---|---|
| 0 | Yedek (`~/Documents/cocuk-shorts-yedek/…tgz`), mevcut testler | 22/22 geçti ✔ |
| 1 | Blender kurulumu + başsız render + Metal doğrulaması | Komut satırından PNG render |
| 2 | **Prototip:** kodla üretilen rig'li 2 karakter (iskelet, göz kırpma, ağız şekil anahtarları), orman seti, yürüme/zıplama/el sallama, 2+ kamera açısı, ışık değişimi; kısa Shorts (9:16) + kısa yatay (16:9) | Kabul testleri 1-4 |
| 3 | Ses: karakter başına ses profili, diyalog zamanlaması, sesle eşleşen ağız hareketi, müzik ducking, efekt; altyazı | Kabul testi 5 |
| 4 | 3D kalite kontrolü: Blender'dan kare kare karakter konumu/kemik açısı/kamera dökümü + kamera görüş alanı içinde mi; siyah/donmuş kare, sahne geçişi, ses senkronu | Kabul testleri 2, 6 |
| 5 | Seri/bölüm proje dosyaları (karakter kimlikleri, ses profilleri, mekânlar, devam eden olaylar), senaryo → sahne/animasyon komutları | Aynı karakter iki bölümde aynı |
| 6 | Üretim kuyruğu: iş durumu, yeniden deneme, çift yayın engeli, disk/süre sınırı, sahne sahne render ve kaldığı yerden devam; yerel zamanlayıcı (launchd) **ayrı onayla** | Kesinti sonrası devam testi |
| 7 | YouTube: yalnız `private`, video başına onay, asgari yetki; herkese açık için ayrı açık onay | Kabul testi 8 |
| 8 | (İsteğe bağlı) ComfyUI/AI video motoru — yalnız prototip onaylanırsa, disk/lisans kontrolüyle | Ayrı rapor |

Prototip (aşama 2-4) kalite kontrolünü geçmeden kuyruk ve uzun bölüm otomasyonuna geçilmez.

## 6. Önemli gerçekler

- Bilgisayar kapalı veya uykudayken hiçbir yerel üretim çalışmaz. Sürekli üretim için ya Mac'in açık
  kalması + launchd zamanlayıcısı, ya da ayrıca onaylanmış bir sunucu gerekir. Blender 3D render GPU'suz
  GitHub Actions makinelerinde pratik değildir; 3D hattı yerel çalışacak.
- Kodla üretilen karakterler "Pixar kalitesi" olmayacak; sade, yuvarlak hatlı, oyuncak tarzı 3D olacak.
  Gerçek iskelet animasyonu, ifade ve kamera dili ise gerçek olacak.
