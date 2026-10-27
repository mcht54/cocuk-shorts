"""Senaryodan dikey (1080x1920) Shorts videosu üretir.

Akış: sahne başına edge-tts seslendirme (kelime zamanlarıyla) -> sahne görseli
(gorsel.py: yapay zekâ ya da yerel çizim, kalite kontrollü) -> PIL ile kare kare
çizim (yakınlaşma, geçiş, kelime vurgulu altyazı) -> ffmpeg'e ham kare akışı +
ses/müzik karışımı. ffmpeg'in libass/drawtext desteğine ihtiyaç duymaz.
Dönen rapor kalite kontrolünde (kalite.py) kullanılır.
"""
import asyncio
import hashlib
import math
import random
import subprocess
import time
import wave
from array import array
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

from . import cizim, gorsel

G, Y = 1080, 1920
FPS = 30
SR = 24000  # edge-tts çıkış örnekleme hızı
KOK = Path(__file__).resolve().parent.parent
FONT = str(KOK / "fonts" / "Baloo2-ExtraBold.ttf")
SES = "tr-TR-EmelNeural"
ALTYAZI_TUT = 1.6  # cümle bitince altyazı en fazla bu kadar ekranda kalır (sn)


# ---------------------------------------------------------------- seslendirme
async def _tts(metin, mp3_yolu, ses=SES, hiz="-6%", perde="+4Hz"):
    c = edge_tts.Communicate(metin, ses, rate=hiz, pitch=perde, boundary="WordBoundary")
    kelimeler = []
    with open(mp3_yolu, "wb") as f:
        async for p in c.stream():
            if p["type"] == "audio":
                f.write(p["data"])
            elif p["type"] == "WordBoundary":
                bas = p["offset"] / 1e7
                kelimeler.append((bas, bas + p["duration"] / 1e7, p["text"]))
    return kelimeler


def seslendir(metin, klasor, ad, ses=SES, hiz="-6%", perde="+4Hz"):
    mp3 = klasor / f"{ad}.mp3"
    wav = klasor / f"{ad}.wav"
    deneme_sayisi = 6  # servis aralıklı "ses yok" dönebiliyor; yine olmazsa açıkça hata
    for deneme in range(deneme_sayisi):
        try:
            kelimeler = asyncio.run(_tts(metin, mp3, ses, hiz, perde))
            if not kelimeler or mp3.stat().st_size < 2000:
                raise RuntimeError("seslendirme boş döndü")
            break
        except Exception:
            if deneme == deneme_sayisi - 1:
                raise
            time.sleep(min(40, 4 * 2 ** deneme))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                    "-ac", "1", "-ar", str(SR), str(wav)], check=True)
    with wave.open(str(wav)) as w:
        ornekler = array("h", w.readframes(w.getnframes()))
    return ornekler, kelimeler


def _noktalama_koru(metin, kelimeler):
    """WordBoundary noktalama vermez; cümle sonlarını altyazı gruplaması için geri koy."""
    jetonlar = metin.split()
    kel = [(a, b, jetonlar[j] if j < len(jetonlar) and t in jetonlar[j] else t)
           for j, (a, b, t) in enumerate(kelimeler)]
    if kel:
        a, b, t = kel[-1]
        kel[-1] = (a, b, t if t[-1:] in ".!?" else t + ".")
    return kel


def _kapla(img, olcek=1.18):
    """Görseli kanvası taşacak şekilde ölçekle (yakınlaşma payıyla)."""
    w, h = img.size
    k = max(G * olcek / w, Y * olcek / h)
    return img.resize((int(w * k), int(h * k)), Image.LANCZOS)


# ---------------------------------------------------------------- müzik
def muzik(ornek_sayisi, tohum):
    """Hafif müzik kutusu arpejleri (telifsiz, kodla üretilir). Tam ornek_sayisi uzunluğunda."""
    r = random.Random(tohum)
    n = ornek_sayisi
    sure = n / SR
    buf = array("f", bytes(4 * n))
    kok = r.choice([60, 62, 65, 67])
    akorlar = [[0, 4, 7, 12], [-3, 0, 4, 9], [5, 9, 12, 17], [7, 11, 14, 19]]
    vurus = 60 / r.choice([92, 100, 108]) / 2
    t, i = 0.0, 0
    while t < sure:
        akor = akorlar[(i // 8) % 4]
        nota = kok + akor[r.choice([0, 1, 2, 3, i % 4])]
        f = 440 * 2 ** ((nota - 69) / 12)
        bas = int(t * SR)
        uz = min(int(1.4 * SR), n - bas)
        for j in range(0, uz):
            tt = j / SR
            buf[bas + j] += 0.18 * math.exp(-3.2 * tt) * (math.sin(2 * math.pi * f * tt)
                                                           + 0.3 * math.sin(4 * math.pi * f * tt))
        t += vurus
        i += 1
    return buf


def karistir(ses, m):
    """Konuşma + müzik; müzik son 1.2 sn'de kısılır. İkisi aynı uzunlukta olmalı."""
    if len(ses) != len(m):
        raise ValueError(f"ses ({len(ses)}) ve müzik ({len(m)}) uzunlukları farklı")
    ham = array("f", bytes(4 * len(ses)))
    for j in range(len(ses)):
        sonda = min(1.0, (len(ses) - j) / (1.2 * SR))
        ham[j] = ses[j] + m[j] * 32767 * 0.32 * sonda
    tepe = max(1.0, max(abs(x) for x in ham))
    kazanc = min(1.0, 29000 / tepe)  # en fazla ≈ -1 dBFS; kırpılma olmasın
    return array("h", (int(x * kazanc) for x in ham))


# ---------------------------------------------------------------- altyazı
def parcala(kelimeler, en_cok=3):
    """Kelimeleri ekranda birlikte görünecek 2-3'lük gruplara böl; cümle sınırını aşma."""
    gruplar, akt = [], []
    for k in kelimeler:
        akt.append(k)
        if len(akt) >= en_cok or k[2].rstrip()[-1:] in ".,!?" or sum(len(x[2]) for x in akt) > 16:
            gruplar.append(akt)
            akt = []
    if akt:
        gruplar.append(akt)
    return gruplar


def altyazi_zaman_cizelgesi(gruplar, sure):
    """Her kare için gösterilecek grup indeksini (ya da None) döndürür."""
    cizelge, gi = [], 0
    for k in range(int(sure * FPS)):
        t = k / FPS
        while gi + 1 < len(gruplar) and gruplar[gi + 1][0][0] <= t:
            gi += 1
        goster = gruplar and gruplar[gi][0][0] - 0.2 <= t <= gruplar[gi][-1][1] + ALTYAZI_TUT
        cizelge.append(gi if goster else None)
    return cizelge


def altyazi_olcum(kelimeler, gruplar, cizelge):
    """Gösterilmeyen kelime sayısı ve konuşma süresince altyazısız en uzun boşluk."""
    gosterilen = set()
    grup_bas = {}
    say = 0
    for gi, g in enumerate(gruplar):
        grup_bas[gi] = say
        say += len(g)
    for k, gi in enumerate(cizelge):
        if gi is None:
            continue
        t = k / FPS
        for j, (bas, son, _) in enumerate(gruplar[gi]):
            if bas - 1 / FPS <= t <= son + 1 / FPS:  # kelime söylenirken ekranda
                gosterilen.add(grup_bas[gi] + j)
    ilk, son = kelimeler[0][0], kelimeler[-1][1]
    en_uzun = akt = 0
    for k, gi in enumerate(cizelge):
        t = k / FPS
        if ilk <= t <= son and gi is None:
            akt += 1
            en_uzun = max(en_uzun, akt)
        else:
            akt = 0
    return {"kelime": len(kelimeler), "gosterilmeyen": len(kelimeler) - len(gosterilen),
            "en_uzun_bosluk_sn": round(en_uzun / FPS, 2)}


def _altyazi(d, grup, simdi, font):
    ust = Y * 0.66
    bosluk = 22
    parcalar = [g[2] for g in grup]
    genislik = [d.textlength(p, font=font) for p in parcalar]
    toplam = sum(genislik) + bosluk * (len(parcalar) - 1)
    satirlar = [list(range(len(parcalar)))]
    if toplam > G * 0.86:  # iki satıra böl
        satirlar = [list(range(len(parcalar) - 1)), [len(parcalar) - 1]]
    for si, satir in enumerate(satirlar):
        sw = sum(genislik[i] for i in satir) + bosluk * (len(satir) - 1)
        x = (G - sw) / 2
        yy = ust + si * font.size * 1.15
        for i in satir:
            bas, son, _ = grup[i]
            aktif = bas <= simdi < max(son, bas + 0.12)
            renk = (255, 214, 10) if aktif else (255, 255, 255)
            kalk = -10 if aktif else 0
            d.text((x, yy + kalk), parcalar[i], font=font, fill=renk,
                   stroke_width=10, stroke_fill=(40, 30, 90))
            x += genislik[i] + bosluk


def _baslik(d, metin, font):
    satirlar, akt = [], ""
    for k in metin.split():
        deneme = (akt + " " + k).strip()
        if d.textlength(deneme, font=font) > G * 0.84 and akt:
            satirlar.append(akt)
            akt = k
        else:
            akt = deneme
    satirlar.append(akt)
    yy = Y * 0.11
    for s in satirlar:
        w = d.textlength(s, font=font)
        d.text(((G - w) / 2, yy), s, font=font, fill=(255, 255, 255),
               stroke_width=12, stroke_fill=(232, 72, 120))
        yy += font.size * 1.1


# ---------------------------------------------------------------- ana işlev
def uret(senaryo, cikti, is_klasoru, kota=None):
    """Videoyu üretir, ölçüm raporunu döndürür. Kalite kararını kalite.py verir."""
    is_klasoru = Path(is_klasoru)
    is_klasoru.mkdir(parents=True, exist_ok=True)
    kota = kota or gorsel.Kota()
    tohum = int(hashlib.md5(senaryo["baslik"].encode()).hexdigest()[:8], 16)
    karakter_tarifi = senaryo.get("karakter_tarifi", "")
    karakter_ogesi = senaryo.get("karakter_ogesi") or cizim.ana_karakter(senaryo)
    bosluk = array("h", bytes(2 * int(0.35 * SR)))

    ses = array("h", bytes(2 * int(0.25 * SR)))
    sahneler, kelimeler, gorsel_rapor = [], [], []
    ortam = "cayir"
    for i, s in enumerate(senaryo["sahneler"]):
        orn, kel = seslendir(s["metin"], is_klasoru, f"s{i}")
        bas = len(ses) / SR
        kelimeler += [(bas + a, bas + b, t) for a, b, t in _noktalama_koru(s["metin"], kel)]
        ses += orn + bosluk
        img, rapor, ortam = gorsel.sahne_gorseli(s, karakter_tarifi, karakter_ogesi,
                                                 tohum + i, ortam, kota)
        rapor["sahne"] = i
        gorsel_rapor.append(rapor)
        print(f"sahne {i}: görsel={rapor['kaynak']} ortam={ortam} {'; '.join(rapor['notlar'])}",
              flush=True)
        sahneler.append({"bas": bas, "gorsel": _kapla(img)})
    ses += array("h", bytes(2 * int(0.6 * SR)))
    sure = len(ses) / SR
    for i, s in enumerate(sahneler):
        s["son"] = sahneler[i + 1]["bas"] if i + 1 < len(sahneler) else sure

    m = muzik(len(ses), tohum)
    ses_yolu = is_klasoru / "karisim.wav"
    with wave.open(str(ses_yolu), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(karistir(ses, m).tobytes())

    font = ImageFont.truetype(FONT, 92)
    baslik_font = ImageFont.truetype(FONT, 104)
    gruplar = parcala(kelimeler)
    cizelge = altyazi_zaman_cizelgesi(gruplar, sure)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{G}x{Y}", "-r", str(FPS), "-i", "-", "-i", str(ses_yolu),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(cikti)],
        stdin=subprocess.PIPE)

    def sahne_karesi(si, t):
        s = sahneler[si]
        img = s["gorsel"]
        ilerleme = min(1.0, max(0.0, (t - s["bas"]) / max(0.1, s["son"] - s["bas"])))
        z = 1.03 + 0.14 * (ilerleme if si % 2 == 0 else 1 - ilerleme)
        cw = min(img.width, img.height * G / Y) / z
        ch = cw * Y / G
        cx = (img.width - cw) / 2 + (ilerleme - 0.5) * (img.width - cw) * 0.4 * (1 if si % 2 else -1)
        cy = (img.height - ch) / 2
        return img.resize((G, Y), Image.BILINEAR, box=(cx, cy, cx + cw, cy + ch))

    for k, gi in enumerate(cizelge):
        t = k / FPS
        si = max(i for i, s in enumerate(sahneler) if s["bas"] <= t or i == 0)
        kare = sahne_karesi(si, t)
        if si > 0 and t - sahneler[si]["bas"] < 0.3:  # yumuşak geçiş
            kare = Image.blend(sahne_karesi(si - 1, t), kare, (t - sahneler[si]["bas"]) / 0.3)
        d = ImageDraw.Draw(kare)
        if t < 2.8:
            _baslik(d, senaryo["ekran_basligi"], baslik_font)
        if gi is not None:
            _altyazi(d, gruplar[gi], t, font)
        ff.stdin.write(kare.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg kodlama hatası")

    return {
        "sure": round(sure, 3),
        "ses_ornek": len(ses), "muzik_ornek": len(m),
        "konusma_son": round(kelimeler[-1][1], 3),
        "sahne_baslari": [round(s["bas"], 3) for s in sahneler],
        "altyazi": altyazi_olcum(kelimeler, gruplar, cizelge),
        "gorseller": gorsel_rapor,
        "cf_noron": round(kota.cf_kullanilan, 1),
    }
