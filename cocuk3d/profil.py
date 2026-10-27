"""Video profilleri: Shorts (9:16) ve uzun bölüm (16:9). İkisi de aynı seri/karakter/
dünya tanımlarını kullanır; yalnız kadraj, süre sınırı ve kurgu kuralları değişir."""

PROFILLER = {
    "shorts": {
        "en": 1080, "boy": 1920, "fps": 24,
        "x_sikistir": 0.75,           # dar dikey kadraj için yatay mesafeleri kısalt
        "sure": [15.0, 59.0],
        "baslik_karti": True,         # ilk 2.5 sn ekranda kanca başlık
        "giris_cekimi": False,
        "altyazi_olcek": 1.0,
    },
    "uzun": {
        "en": 1920, "boy": 1080, "fps": 24,
        "x_sikistir": 1.0,
        # Uzun bölüm hedefi birkaç dakika; prototip bölüm kısa olduğu için alt sınır
        # PROTOTIP_UZUN_EN_AZ ile düşürülebilir ve raporda "prototip" olarak işaretlenir.
        "sure": [60.0, 1800.0],
        "baslik_karti": False,
        "giris_cekimi": True,         # seri adı + bölüm adı anlatıcıyla açılış çekimi
        "altyazi_olcek": 0.62,
    },
}
PROTOTIP_UZUN_EN_AZ = 20.0


def profil(ad, prototip=False):
    p = dict(PROFILLER[ad], ad=ad)
    if prototip and ad == "uzun":
        p["sure"] = [PROTOTIP_UZUN_EN_AZ, p["sure"][1]]
        p["prototip"] = True
    return p
