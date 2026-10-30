"""Merak Arşivi özgün hareketli grafikleri (kodla çizilir, hiçbir dış görsele dayanmaz).

Türler (senaryoda parça "grafik" alanı):
  {"tur": "harita", "etiket": "Derinkuyu"}                       -> dünyadan konuma yakınlaşan harita
  {"tur": "zaman", "olaylar": [{"yil": "1963", "metin": "..."}]}  -> sırayla beliren zaman çizelgesi
  {"tur": "sayi", "deger": "85", "birim": "metre", "metin": "..."} -> sayaç
  {"tur": "karsilastirma", "deger": 85, "birim": "m", "etiket": "...", "referans": "eyfel"} -> boy karşılaştırma
Harita verisi: Natural Earth (kamu malı). Karşılaştırma referansları aşağıdaki sabit, doğrulanmış tablodan.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

KOK = Path(__file__).resolve().parent
FONT = KOK.parent / "fonts" / "Montserrat-wght.ttf"
ARKA, KARA, DENIZ, VURGU, YAZI = (14, 18, 28), (48, 58, 74), (20, 30, 46), (232, 168, 60), (240, 240, 240)
# yükseklik/uzunluk (metre); yalnız iyi bilinen, sabit değerler
REFERANSLAR = {
    "eyfel": ("Eyfel Kulesi", 330), "ozgurluk_aniti": ("Özgürlük Anıtı", 93), "galata": ("Galata Kulesi", 63),
    "futbol_sahasi": ("Futbol sahası (boy)", 105), "bina_10_kat": ("10 katlı bina", 30),
    "insan": ("İnsan", 1.7), "otobus": ("Otobüs (boy)", 12), "mavi_balina": ("Mavi balina", 30),
    "burj_halife": ("Burc Halife", 828), "keops": ("Keops Piramidi (bugün)", 139),
}
TR_HARF = str.maketrans("iı", "İI")


def ust(m):
    return m.translate(TR_HARF).upper()


@lru_cache(maxsize=32)
def font(boyut, agirlik=800):
    f = ImageFont.truetype(str(FONT), int(boyut))
    f.set_variation_by_axes([agirlik])
    return f


@lru_cache(maxsize=1)
def ulkeler():
    d = json.loads((KOK / "veri" / "ulkeler.geojson").read_text())
    out = []
    for f in d["features"]:
        g = f["geometry"]
        polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        out.append([p[0] for p in polis])
    return out


def _icinde(lon, lat, halka):
    ic, j = False, len(halka) - 1
    for i in range(len(halka)):
        xi, yi = halka[i]
        xj, yj = halka[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi:
            ic = not ic
        j = i
    return ic


@lru_cache(maxsize=8)
def _ulke_no(lon, lat):
    for n, halkalar in enumerate(ulkeler()):
        if any(_icinde(lon, lat, h) for h in halkalar):
            return n
    return None


def _yumusak(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _zemin(en, boy):
    im = Image.new("RGB", (en, boy), ARKA)
    d = ImageDraw.Draw(im)
    for x in range(0, en, 60):
        d.line((x, 0, x, boy), fill=(20, 25, 37))
    for y in range(0, boy, 60):
        d.line((0, y, en, y), fill=(20, 25, 37))
    return im


def harita(spec, u, en, boy, koordinat):
    lat, lon = koordinat
    z = _yumusak(u / 0.6)  # ilk %60'ta dünyadan bölgeye yakınlaş
    gen = 360 * (1 - z) + 16 * z           # görünen boylam genişliği
    yuk = gen * boy / en
    merkez_lon = 0 * (1 - z) + lon * z
    merkez_lat = 20 * (1 - z) + lat * z
    sol, alt = merkez_lon - gen / 2, merkez_lat - yuk / 2

    def p(x, y):
        return ((x - sol) / gen * en, boy - (y - alt) / yuk * boy)
    im = Image.new("RGB", (en, boy), DENIZ)
    d = ImageDraw.Draw(im)
    secili = _ulke_no(round(lon, 3), round(lat, 3))
    for n, halkalar in enumerate(ulkeler()):
        for h in halkalar:
            xs = [x for x, _ in h]
            if max(xs) < sol - 5 or min(xs) > sol + gen + 5:
                continue
            d.polygon([p(x, y) for x, y in h], fill=(96, 74, 40) if n == secili else KARA, outline=(78, 92, 112))
    x, y = p(lon, lat)
    a = _yumusak((u - 0.45) / 0.2)
    if a > 0:
        nabiz = 1 + 0.25 * math.sin(u * 30)
        for r, al in ((46 * nabiz, 60), (24, 160)):
            d.ellipse((x - r * a, y - r * a, x + r * a, y + r * a), outline=VURGU + (al,), width=4)
        d.ellipse((x - 11, y - 11, x + 11, y + 11), fill=VURGU)
        f = font(64 if en > boy else 70)
        etiket = ust(spec.get("etiket", ""))
        w = d.textlength(etiket, font=f)
        tx = min(max(30, x - w / 2), en - w - 30)
        ty = y - 130 if y > boy * 0.3 else y + 50
        d.rounded_rectangle((tx - 22, ty - 12, tx + w + 22, ty + 82), 14, fill=(0, 0, 0))
        d.text((tx, ty), etiket, font=f, fill=VURGU)
    return im


def zaman(spec, u, en, boy):
    im = _zemin(en, boy)
    d = ImageDraw.Draw(im)
    olaylar = spec.get("olaylar", [])[:5]
    n = max(1, len(olaylar))
    yatay = en > boy
    f_yil, f_m = font(58 if yatay else 64), font(34 if yatay else 40, 600)
    if yatay:
        y0, x0, x1 = boy * 0.5, en * 0.08, en * 0.92
        d.line((x0, y0, x0 + (x1 - x0) * _yumusak(u / 0.25), y0), fill=(110, 120, 140), width=6)
    else:
        x0, y0, y1 = en * 0.16, boy * 0.08, boy * 0.60  # alt kısım altyazının
        d.line((x0, y0, x0, y0 + (y1 - y0) * _yumusak(u / 0.25)), fill=(110, 120, 140), width=6)
    for i, o in enumerate(olaylar):
        a = _yumusak((u - 0.15 - i * 0.7 / n) / 0.12)
        if a <= 0:
            continue
        renk = tuple(int(c * a + ARKA[k] * (1 - a)) for k, c in enumerate(VURGU))
        beyaz = tuple(int(c * a + ARKA[k] * (1 - a)) for k, c in enumerate(YAZI))
        if yatay:
            x = x0 + (x1 - x0) * (i + 0.5) / n
            d.ellipse((x - 16, y0 - 16, x + 16, y0 + 16), fill=renk)
            yil = ust(str(o.get("yil", "")))
            d.text((x - d.textlength(yil, font=f_yil) / 2, y0 - 110 if i % 2 == 0 else y0 + 40), yil,
                   font=f_yil, fill=renk)
            satirlar = _satirla(d, o.get("metin", ""), f_m, (x1 - x0) / n * 0.98)[:4]
            ty = y0 + 120 if i % 2 == 0 else y0 - 120 - 44 * len(satirlar)
            for j, s in enumerate(satirlar):
                d.text((x - d.textlength(s, font=f_m) / 2, ty + j * 44), s, font=f_m, fill=beyaz)
        else:
            y = y0 + (y1 - y0) * (i + 0.5) / n
            d.ellipse((x0 - 18, y - 18, x0 + 18, y + 18), fill=renk)
            d.text((x0 + 50, y - 70), ust(str(o.get("yil", ""))), font=f_yil, fill=renk)
            for j, s in enumerate(_satirla(d, o.get("metin", ""), f_m, en * 0.7)[:2]):
                d.text((x0 + 50, y + 4 + j * 48), s, font=f_m, fill=beyaz)
    return im


def _satirla(d, metin, f, genislik):
    satirlar, akt = [], ""
    for k in str(metin).split():
        dd = (akt + " " + k).strip()
        if d.textlength(dd, font=f) > genislik and akt:
            satirlar.append(akt)
            akt = k
        else:
            akt = dd
    return satirlar + ([akt] if akt else [])


def _sayi_yaz(deger, u):
    """'20.000' -> sayarak artan metin (binlik ayıracı korunur)."""
    temiz = str(deger).replace(".", "").replace(",", "")
    if not temiz.isdigit():
        return str(deger)
    hedef = int(temiz)
    simdi = int(hedef * _yumusak(u / 0.55))
    return f"{simdi:,}".replace(",", ".") if hedef >= 1000 else str(simdi)


def sayi(spec, u, en, boy):
    im = _zemin(en, boy)
    d = ImageDraw.Draw(im)
    f_s, f_b, f_m = font(260 if en > boy else 230, 900), font(80, 700), font(48 if en > boy else 54, 600)
    metin = _sayi_yaz(spec.get("deger", ""), u)
    w = d.textlength(metin, font=f_s)
    y = boy * (0.28 if en > boy else 0.33)
    d.text(((en - w) / 2, y), metin, font=f_s, fill=VURGU)
    birim = ust(str(spec.get("birim", "")))
    d.text(((en - d.textlength(birim, font=f_b)) / 2, y + f_s.size * 1.05), birim, font=f_b, fill=YAZI)
    a = _yumusak((u - 0.4) / 0.2)
    if a > 0:
        renk = tuple(int(c * a + ARKA[k] * (1 - a)) for k, c in enumerate(YAZI))
        for j, s in enumerate(_satirla(d, spec.get("metin", ""), f_m, en * 0.8)[:3]):
            d.text(((en - d.textlength(s, font=f_m)) / 2, y + f_s.size * 1.05 + 130 + j * 64), s, font=f_m, fill=renk)
    return im


def karsilastirma(spec, u, en, boy):
    im = _zemin(en, boy)
    d = ImageDraw.Draw(im)
    ref_ad, ref = REFERANSLAR[spec["referans"]]
    deger = float(str(spec["deger"]).replace(",", "."))
    en_buyuk = max(deger, ref)
    taban, tavan = (boy * 0.82, boy * 0.22) if en > boy else (boy * 0.56, boy * 0.12)  # dikeyde altyazıya yer
    f_d, f_e = font(64 if en > boy else 60, 800), font(40 if en > boy else 42, 600)
    g = _yumusak(u / 0.5)
    for i, (ad, v, renk) in enumerate(((spec.get("etiket", ""), deger, VURGU), (ref_ad, ref, (120, 150, 190)))):
        x = en * (0.32 + 0.36 * i)
        bw = en * (0.16 if en > boy else 0.22)
        h = (taban - tavan) * v / en_buyuk * g
        d.rectangle((x - bw / 2, taban - h, x + bw / 2, taban), fill=renk)
        sayi_m = f"{v:g} {spec.get('birim', 'm')}".replace(".", ",")
        d.text((x - d.textlength(sayi_m, font=f_d) / 2, taban - h - 90), sayi_m, font=f_d, fill=YAZI)
        for j, s in enumerate(_satirla(d, ad, f_e, bw * 1.6)[:2]):
            d.text((x - d.textlength(s, font=f_e) / 2, taban + 24 + j * 50), s, font=f_e, fill=YAZI)
    d.line((en * 0.08, taban, en * 0.92, taban), fill=(110, 120, 140), width=4)
    return im


def ciz(spec, u, en, boy, koordinat=None):
    tur = spec.get("tur")
    if tur == "harita" and koordinat:
        return harita(spec, u, en, boy, koordinat)
    if tur == "zaman":
        return zaman(spec, u, en, boy)
    if tur == "sayi":
        return sayi(spec, u, en, boy)
    if tur == "karsilastirma" and spec.get("referans") in REFERANSLAR:
        return karsilastirma(spec, u, en, boy)
    raise ValueError(f"çizilemeyen grafik: {spec}")


def kredi(spec):
    return "Harita: Merak Arşivi · veri Natural Earth" if spec.get("tur") == "harita" else "Grafik: Merak Arşivi"
