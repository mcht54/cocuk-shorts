# YouTube bağlantısı — bir kerelik (≈20 dk)

Bunu yalnız kanal sahibi yapabilir (Google, kanala erişim iznini sahibinden ister). Sonrasında
hiçbir şeye dokunmak gerekmez.

## 1. Google Cloud projesi (5 dk)

1. https://console.cloud.google.com/projectcreate → Proje adı: `findik-ile-pamuk` → **Oluştur**
2. https://console.cloud.google.com/apis/library/youtube.googleapis.com → **Etkinleştir**
3. Faturalandırma (billing) **açmayın**; gerekmez.

## 2. İzin ekranı (5 dk)

https://console.cloud.google.com/auth/overview → **Başlayın**

- Uygulama adı: `Fındık ile Pamuk Yükleyici` — destek e-postası: kanal hesabınız
- Kitle: **Harici (External)**
- İletişim e-postası: kanal hesabınız → **Oluştur**
- Sol menü **Kitle (Audience)** → **Uygulamayı yayınla (Publish app)** → Onayla
  (Yapılmazsa izin 7 günde düşer.)

## 3. İstemci kimliği (2 dk)

https://console.cloud.google.com/auth/clients → **İstemci oluştur** → Uygulama türü:
**Masaüstü uygulaması** → Ad: `yukleyici` → **Oluştur** → **JSON'u indir**

İndirilen dosyayı `~/Documents/cocuk-shorts/` klasörüne koyun (adı `client_secret_....json`).
Claude gerisini yapar: izin betiğini çalıştırır, tarayıcıda kanal hesabıyla **İzin ver** demeniz
yeterli ("Google bu uygulamayı doğrulamadı" uyarısında **Gelişmiş → devam et**). Anahtarlar
GitHub'ın gizli kasasına (Secrets) girer, bilgisayarda/kodda kalmaz.

## 4. YouTube API denetim başvurusu (8 dk)

Denetimden geçmemiş projelerin yüklediği videoları YouTube **gizli (private) kilitler**; herkese
açık yayın için bu başvuru şart. Form: https://support.google.com/youtube/contact/yt_api_form

Formda istenirse kullanılacak hazır cevaplar:

- **API projesi numarası:** Cloud Console ana sayfasındaki "Proje numarası"
- **Kullanım amacı:** "Single-channel internal tool. It uploads our own original 3D animated
  children's episodes ('Fındık ile Pamuk') to our own YouTube channel once per day. No other
  users, no data collection, no third-party channels."
- **Kullanılan API'ler:** `videos.insert` (only), scope `youtube.upload`
- **Kullanıcı sayısı:** 1 (only the channel owner)
- **Veri saklama:** "We store no YouTube user data. Only the uploaded video ID is logged in our
  own repository."
- **İçerik:** "Original, self-produced animation, self-declared Made for Kids (COPPA)."
- **Kod/ekran görüntüsü istenirse:** https://github.com/mcht54/cocuk-shorts

Onay e-postası gelince Claude'a haber verin: herkese açık yayını açar ve günlük zamanlamayı başlatır.
