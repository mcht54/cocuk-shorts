"""Render edilmiş kareler + altyazı + (Shorts) kanca başlığı + ses -> MP4.

Altyazı satır satır gruplanır (bir grup iki konuşmacıyı karıştırmaz), söylenen kelime
konuşan karakterin rengiyle vurgulanır.
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cocuk import video

RENKLER = {"findik": (255, 168, 60), "pamuk": (255, 140, 200), "anlatici": (255, 214, 10)}
ALTYAZI_TUT = 1.6


def gruplar_olustur(kelimeler):
    """Kelimeleri satır/konuşmacı sınırını aşmadan 2-3'lük gruplara böl."""
    gruplar, satir = [], []
    for k in kelimeler:
        if satir and (k["kim"] != satir[-1]["kim"] or k["bas"] - satir[-1]["son"] > 0.25):
            gruplar += [[(w["bas"], w["son"], w["metin"], w["kim"]) for w in g]
                        for g in _parcala_sozluk(satir)]
            satir = []
        satir.append(k)
    if satir:
        gruplar += [[(w["bas"], w["son"], w["metin"], w["kim"]) for w in g] for g in _parcala_sozluk(satir)]
    return gruplar


def _parcala_sozluk(satir):
    demetler = [(w["bas"], w["son"], w["metin"]) for w in satir]
    sonuc, i = [], 0
    for g in video.parcala(demetler):
        sonuc.append(satir[i:i + len(g)])
        i += len(g)
    return sonuc


def zaman_cizelgesi(gruplar, kare_say, fps):
    cizelge, gi = [], 0
    for k in range(kare_say):
        t = k / fps
        while gi + 1 < len(gruplar) and gruplar[gi + 1][0][0] <= t:
            gi += 1
        goster = bool(gruplar) and gruplar[gi][0][0] - 0.2 <= t <= gruplar[gi][-1][1] + ALTYAZI_TUT
        cizelge.append(gi if goster else None)
    return cizelge


def altyazi_olcum(gruplar, cizelge, fps, satirlar):
    """Söylenirken görünmeyen kelime sayısı; satır içinde altyazısız en uzun süre."""
    gosterilen, toplam = set(), 0
    for gi, g in enumerate(gruplar):
        toplam += len(g)
    sira = {}
    say = 0
    for gi, g in enumerate(gruplar):
        sira[gi] = say
        say += len(g)
    for k, gi in enumerate(cizelge):
        if gi is None:
            continue
        t = k / fps
        for j, w in enumerate(gruplar[gi]):
            if w[0] - 1 / fps <= t <= w[1] + 1 / fps:
                gosterilen.add(sira[gi] + j)
    en_uzun = 0
    for s in satirlar:
        akt = 0
        for k in range(int(s["bas"] * fps), min(len(cizelge), int(s["son"] * fps))):
            akt = akt + 1 if cizelge[k] is None else 0
            en_uzun = max(en_uzun, akt)
    return {"kelime": toplam, "gosterilmeyen": toplam - len(gosterilen),
            "en_uzun_bosluk_sn": round(en_uzun / fps, 2)}


def _ciz_altyazi(d, grup, t, font, en, boy, oran_y):
    bosluk = int(font.size * 0.24)
    parcalar = [w[2] for w in grup]
    gen = [d.textlength(p, font=font) for p in parcalar]
    satirlar = [list(range(len(parcalar)))]
    if sum(gen) + bosluk * (len(gen) - 1) > en * 0.86:
        satirlar = [list(range(len(parcalar) - 1)), [len(parcalar) - 1]]
    for si, satir in enumerate(satirlar):
        sw = sum(gen[i] for i in satir) + bosluk * (len(satir) - 1)
        x = (en - sw) / 2
        y = boy * oran_y + si * font.size * 1.15
        for i in satir:
            bas, son, _, kim = grup[i]
            aktif = bas <= t < max(son, bas + 0.12)
            renk = RENKLER.get(kim, (255, 214, 10)) if aktif else (255, 255, 255)
            d.text((x, y - (font.size * 0.1 if aktif else 0)), parcalar[i], font=font, fill=renk,
                   stroke_width=max(4, font.size // 9), stroke_fill=(40, 30, 90))
            x += gen[i] + bosluk


def _ciz_baslik(d, metin, font, en, boy):
    satirlar, akt = [], ""
    for k in metin.split():
        dd = (akt + " " + k).strip()
        if d.textlength(dd, font=font) > en * 0.84 and akt:
            satirlar.append(akt)
            akt = k
        else:
            akt = dd
    satirlar.append(akt)
    y = boy * 0.09
    for s in satirlar:
        w = d.textlength(s, font=font)
        d.text(((en - w) / 2, y), s, font=font, fill=(255, 255, 255),
               stroke_width=max(5, font.size // 8), stroke_fill=(232, 72, 120))
        y += font.size * 1.1


def birlestir(is_dizini, cikti):
    is_dizini = Path(is_dizini)
    kurgu = json.loads((is_dizini / "kurgu.json").read_text())
    fps, n = kurgu["fps"], kurgu["kare_say"]
    prof = kurgu["profil"]
    ilk = Image.open(is_dizini / "kareler" / "k_0000.png")
    en, boy = ilk.size
    olcek = en / prof["en"]
    font = ImageFont.truetype(video.FONT, max(18, int(92 * prof["altyazi_olcek"] * olcek
                                                    * (prof["en"] / 1080 if prof["en"] > prof["boy"] else 1))))
    bfont = ImageFont.truetype(video.FONT, max(20, int(104 * olcek)))
    oran_y = 0.70 if prof["boy"] > prof["en"] else 0.80
    gruplar = gruplar_olustur(kurgu["kelimeler"])
    cizelge = zaman_cizelgesi(gruplar, n, fps)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{en}x{boy}", "-r", str(fps), "-i", "-", "-i", str(is_dizini / "ses.wav"),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(cikti)],
        stdin=subprocess.PIPE)
    for k in range(n):
        yol = is_dizini / "kareler" / f"k_{k:04d}.png"
        kare = Image.open(yol).convert("RGB")
        if kare.size != (en, boy):
            raise RuntimeError(f"kare {k} boyutu farklı: {kare.size}")
        d = ImageDraw.Draw(kare)
        t = k / fps
        if prof.get("baslik_karti") and t < 2.5:
            _ciz_baslik(d, kurgu["baslik"], bfont, en, boy)
        if cizelge[k] is not None:
            _ciz_altyazi(d, gruplar[cizelge[k]], t, font, en, boy, oran_y)
        ff.stdin.write(kare.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg kodlama hatası")
    return altyazi_olcum(gruplar, cizelge, fps, kurgu["satirlar"])
