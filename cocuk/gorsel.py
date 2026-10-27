"""Sahne görseli: yapay zekâ (Cloudflare FLUX, isteğe bağlı Pollinations) -> kalite
kontrolü -> başarısızsa yerel çizim (cizim.py). Her sahne bağımsızdır; bir sahnenin
hatası diğerlerini etkilemez. Ücretli servise asla geçilmez.
"""
import base64
import io
import os
import urllib.parse

import requests
from PIL import Image, ImageFilter, ImageStat

from . import cizim

GORSEL_STIL = (", cute children's picture book illustration, soft pastel colors, "
               "warm friendly lighting, simple shapes, wholesome, no text, no letters")

# Cloudflare fiyat sayfası (2026-10): flux-1-schnell 4.80 nöron / 512x512 karo + 9.60 nöron / adım.
# Ücretsiz kota günde 10.000 nöron; varsayılan sınırımız bunun %40'ı.
CF_ADIM = 6
CF_NORON_GORSEL = 4 * 4.80 + CF_ADIM * 9.60  # 1024x1024 = 4 karo


class Kota:
    """Bir çalıştırmadaki ücretsiz servis kullanımını izler; sınırda durur."""

    def __init__(self, cf_bugun=0.0, cf_sinir=None):
        self.cf_kullanilan = 0.0
        self.cf_bugun = cf_bugun
        self.cf_sinir = cf_sinir if cf_sinir is not None else float(os.environ.get("CF_GUNLUK_NORON", 4000))
        self.cf_kapali = False      # hata/kota sonrası bu çalıştırmada bir daha denenmez
        self.pol_kapali = os.environ.get("POLLINATIONS", "0") != "1"

    def cf_izin(self):
        return (not self.cf_kapali
                and self.cf_bugun + self.cf_kullanilan + CF_NORON_GORSEL <= self.cf_sinir)


def gorsel_kontrol(img, en_az_kenar=400):
    """Görselin gerçek bir çizim olup olmadığını ölçer (düz renk/degrade/bozuk değil)."""
    kucuk = img.convert("RGB").resize((270, 480))
    gri = kucuk.convert("L")
    sapma = ImageStat.Stat(gri).stddev[0]
    kenar = ImageStat.Stat(gri.filter(ImageFilter.FIND_EDGES)).mean[0]
    renkler = kucuk.quantize(64).getcolors() or []
    toplam = sum(n for n, _ in renkler)
    baskin = max(n for n, _ in renkler) / toplam if renkler else 1
    anlamli = sum(1 for n, _ in renkler if n / toplam > 0.003)
    olcum = {"sapma": round(sapma, 1), "kenar": round(kenar, 2),
             "baskin_renk": round(baskin, 2), "renk_sayisi": anlamli,
             "boyut": list(img.size)}
    hatalar = []
    if min(img.size) < en_az_kenar:
        hatalar.append("çözünürlük düşük")
    if sapma < 18:
        hatalar.append("kontrast yok (düz/boş görsel)")
    if kenar < 4.2:  # ölçüm: eski degrade 2.99, yerel çizimler ≥ 5.4, AI görseli 8.7
        hatalar.append("çizgi/ayrıntı yok (degrade ya da bulanık)")
    if baskin > 0.6:
        hatalar.append("tek renk baskın")
    if anlamli < 10:
        hatalar.append("renk çeşitliliği yok")
    return not hatalar, olcum, hatalar


def _cloudflare(istem, tohum, kota, kayit):
    hesap, anahtar = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (hesap and anahtar):
        kayit.append("cloudflare: anahtar yok")
        return None
    if not kota.cf_izin():
        kayit.append("cloudflare: günlük nöron sınırı/devre dışı")
        return None
    model = os.environ.get("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
    for deneme in range(2):
        try:
            r = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{hesap}/ai/run/{model}",
                headers={"Authorization": f"Bearer {anahtar}"},
                json={"prompt": istem + GORSEL_STIL + ", vertical composition, subject centered",
                      "steps": CF_ADIM, "seed": tohum % 2**31},
                timeout=90)
            kota.cf_kullanilan += CF_NORON_GORSEL
            if r.ok:
                return Image.open(io.BytesIO(base64.b64decode(r.json()["result"]["image"]))).convert("RGB")
            kayit.append(f"cloudflare: HTTP {r.status_code} {r.text[:160]}")
            if r.status_code in (401, 403, 429) or "quota" in r.text.lower() or "limit" in r.text.lower():
                kota.cf_kapali = True  # yetki/kota sorunu: bu çalıştırmada tekrar deneme
                return None
        except Exception as e:  # ağ hatası
            kayit.append(f"cloudflare: {type(e).__name__}: {e}")
    kota.cf_kapali = True
    return None


def _pollinations(istem, tohum, kota, kayit):
    if kota.pol_kapali:
        return None
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(istem + GORSEL_STIL)
           + f"?width=768&height=1344&nologo=true&seed={tohum}")
    try:
        r = requests.get(url, timeout=45)
        if r.ok and r.headers.get("content-type", "").startswith("image"):
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            w, h = img.size
            return img.crop((0, 0, w, int(h * 0.93)))  # alttaki servis logosunu at
        kayit.append(f"pollinations: HTTP {r.status_code}")
    except Exception as e:
        kayit.append(f"pollinations: {type(e).__name__}")
    kota.pol_kapali = True
    return None


def sahne_gorseli(sahne, karakter_tarifi, karakter_ogesi, tohum, onceki_ortam, kota):
    """(görsel, rapor, ortam) döndürür. Her durumda kalite kontrolünden geçmiş bir görsel verir."""
    kayit = []
    istem = (karakter_tarifi + ". " if karakter_tarifi else "") + sahne["gorsel"]
    for kaynak, fn in (("cloudflare", _cloudflare), ("pollinations", _pollinations)):
        img = fn(istem, tohum, kota, kayit)
        if img is None:
            continue
        tamam, olcum, hatalar = gorsel_kontrol(img)
        if tamam:
            ortam = cizim.ortam_bul(sahne["gorsel"], onceki_ortam)
            return img, {"kaynak": kaynak, "olcum": olcum, "notlar": kayit}, ortam
        kayit.append(f"{kaynak}: kalite kontrolü reddetti: {', '.join(hatalar)}")
    img, ortam = cizim.sahne_ciz(sahne, karakter_ogesi, tohum, onceki_ortam)
    tamam, olcum, hatalar = gorsel_kontrol(img)
    if not tamam:
        raise RuntimeError(f"yerel çizim kalite kontrolünü geçemedi: {hatalar}")
    return img, {"kaynak": "yerel", "olcum": olcum, "notlar": kayit}, ortam
