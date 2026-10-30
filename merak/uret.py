"""Merak Arşivi video üretimi: senaryo JSON -> seslendirme, Ken Burns görseller, bölüm kartları, altyazı,
ortam müziği -> MP4 (+ uzun videoda açıklama ve kapak).

Kullanım: python -m merak.uret <konu_kimligi> <senaryo: uzun|kisa1|kisa2...>
Profil senaryodan gelir: "bolumler" varsa yatay uzun belgesel, yoksa dikey Shorts.
Görseller Wikimedia Commons'tan (lisans bilgisiyle) merak/onbellek'e indirilir; her karede yazar+lisans görünür.
"""
import json
import re
import subprocess
import sys
import wave
from array import array
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from cocuk import video  # edge-tts seslendirme + kelime zamanları
from merak import grafik, kaynak

KOK = Path(__file__).resolve().parent
DEPO = KOK.parent
FPS = 25
SR = video.SR
SES = "tr-TR-AhmetNeural"
PARCA_ARASI, BOLUM_ARASI, GECIS = 0.45, 1.3, 0.7
FONT = DEPO / "fonts" / "Montserrat-wght.ttf"
DEPO_URL = "https://github.com/mcht54/cocuk-shorts/blob/main/merak/konular"


def font(boyut, agirlik=800):
    f = ImageFont.truetype(str(FONT), int(boyut))
    f.set_variation_by_axes([agirlik])
    return f


def temiz(m):
    return kaynak.temiz(m)


def _norm(k):
    return re.sub(r"[^a-zçğıöşüâîû0-9]", "", k.lower())


def noktala(metin, kelimeler):
    """TTS kelime sınırları noktalama taşımaz: senaryodaki yazımı (noktalama dahil) sırayla eşle."""
    jeton, j, out = metin.split(), 0, []
    for a, b, w in kelimeler:
        for k in range(j, min(j + 4, len(jeton))):
            if _norm(w) and (_norm(jeton[k]).startswith(_norm(w)) or _norm(w) in _norm(jeton[k])):
                out.append((a, b, jeton[k]))
                j = k + 1
                break
        else:
            out.append((a, b, w))
    return out


def hazirla(yol, en, boy, olcek=1.12):
    """Görseli en x boy'u olcek kadar aşan tuvale yerleştir. Dikey tuvalde yatay görsel tam yükseklikte
    ve geniş tutulur (kamera üzerinde yatay gezinir). Oran çok farklıysa bulanık arka plan + tam görsel."""
    im = Image.open(yol).convert("RGB")
    tw, th = int(en * olcek), int(boy * olcek)
    w, h = im.size
    hedef_oran, oran = tw / th, w / h
    dikey = en < boy
    kirp_olur = (oran / hedef_oran) < (3.3 if dikey else 1.35) and (hedef_oran / oran) < 1.35
    if not kirp_olur:
        arka = im.resize((tw, th)).filter(ImageFilter.GaussianBlur(40))
        arka = Image.blend(arka, Image.new("RGB", arka.size, (10, 10, 12)), 0.35)
        on = im.copy()
        on.thumbnail((tw, th), Image.LANCZOS)
        arka.paste(on, ((tw - on.width) // 2, (th - on.height) // 2))
        return arka
    o = max(tw / w, th / h)
    im = im.resize((int(w * o + 1), int(h * o + 1)), Image.LANCZOS)
    gen = min(im.width, int(tw * 2.2)) if dikey else tw  # dikeyde gezinme payı
    x, y = (im.width - gen) // 2, (im.height - th) // 2
    return im.crop((x, y, x + gen, y + th))


def ortam_muzigi(n, tohum):
    """Gizemli, yavaş ortam müziği: minör akor pedleri + yumuşak LFO (telifsiz, kodla üretilir)."""
    r = np.random.default_rng(tohum)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    diziler = [[[45, 52, 57, 60], [41, 48, 53, 57], [43, 50, 55, 59], [40, 47, 52, 55]],
               [[50, 57, 62, 65], [46, 53, 58, 62], [48, 55, 60, 64], [45, 52, 57, 61]],
               [[47, 54, 59, 62], [43, 50, 55, 59], [45, 52, 57, 60], [42, 49, 54, 57]]]
    akorlar = diziler[tohum % len(diziler)]
    sure = 8.0
    for i in range(int(n / SR / sure) + 1):
        b, s = int(i * sure * SR), int(min(n, (i + 1.15) * sure * SR))
        if b >= n:
            break
        tt = t[b:s] - t[b]
        zarf = np.minimum(1, tt / 2.5) * np.minimum(1, (tt[-1] - tt + 1e-3) / 2.5)
        for nota in akorlar[i % 4]:
            f = 440 * 2 ** ((nota - 69) / 12)
            out[b:s] += (0.05 * zarf * np.sin(2 * np.pi * f * tt + r.uniform(0, 6))
                         * (1 + 0.3 * np.sin(2 * np.pi * 0.11 * tt))).astype(np.float32)
    return out


def wav_oku(yol):
    with wave.open(str(yol)) as w:
        return np.array(array("h", w.readframes(w.getnframes())), dtype=np.float32) / 32768


def metin_kutu(d, xy, metin, f, dolgu="white", kutu=(0, 0, 0, 150), pay=18, ortala=False):
    w = d.textlength(metin, font=f)
    x, y = xy
    if ortala:
        x -= w / 2
    asc, desc = f.getmetrics()
    d.rounded_rectangle((x - pay, y - pay * 0.6, x + w + pay, y + asc + desc + pay * 0.6), 12, fill=kutu)
    d.text((x, y), metin, font=f, fill=dolgu)


def satirla(d, metin, f, genislik):
    satirlar, akt = [], ""
    for k in metin.split():
        dd = (akt + " " + k).strip()
        if d.textlength(dd, font=f) > genislik and akt:
            satirlar.append(akt)
            akt = k
        else:
            akt = dd
    return satirlar + [akt]


def zs(x):
    x = int(x)
    return f"{x // 60}:{x % 60:02d}"


def uret(kid, ad, cikti_dizini=None):
    """Videoyu üretir; {'video','aciklama','kapak'?,'sure','profil'} döner."""
    d_konu = KOK / "konular" / kid
    s = json.loads((d_konu / f"{ad}.json").read_text())
    gorseller = json.loads((d_konu / "gorseller.json").read_text())
    uzun = "bolumler" in s
    EN, BOY = (1920, 1080) if uzun else (1080, 1920)
    olc = EN / 1920 if uzun else 1.0
    bolumler = s["bolumler"] if uzun else [{"ad": "", "parcalar": s["parcalar"]}]
    is_d = KOK / "onbellek" / kid / ad
    is_d.mkdir(parents=True, exist_ok=True)
    cikti = Path(cikti_dizini or KOK / "cikti")
    cikti.mkdir(parents=True, exist_ok=True)

    # 0) görseller (yalnız kullanılanlar)
    koordinat = json.loads((d_konu / "kaynak.json").read_text()).get("koordinat")
    for b in bolumler:  # çizilemeyecek grafik (ör. koordinatsız harita) görsele döner
        for p in b["parcalar"]:
            if p.get("grafik"):
                try:
                    grafik.ciz(p["grafik"], 0.5, 320, 180, koordinat)
                except Exception:
                    p.pop("grafik")
    kullanilan = sorted({gi for b in bolumler for p in b["parcalar"] if not p.get("grafik") for gi in p["gorsel"]}
                        | ({s["kapak_gorsel"]} if uzun else set()))
    dosya = {}
    for gi in kullanilan:
        hedef = KOK / "onbellek" / kid / "gorsel" / f"{gi:03d}.img"
        if kaynak.indir(gorseller[gi], hedef):
            try:
                Image.open(hedef).verify()
                dosya[gi] = hedef
            except Exception:
                pass
    if len(dosya) < max(3, 0.7 * len(kullanilan)):
        raise RuntimeError(f"görsellerin çoğu indirilemedi ({len(dosya)}/{len(kullanilan)})")
    yedek = list(dosya)
    for b in bolumler:  # indirilemeyen görselin yerine aynı konudan başka biri
        for i, p in enumerate(b["parcalar"]):
            if not p.get("grafik"):
                p["gorsel"] = [g if g in dosya else yedek[(g + i) % len(yedek)] for g in p["gorsel"]]

    # 1) seslendirme ve zaman çizelgesi
    parcalar, t = [], 0.6 if not uzun else 1.0
    for bi, b in enumerate(bolumler):
        if bi:
            t += BOLUM_ARASI
        b["bas"] = t
        for pi, p in enumerate(b["parcalar"]):
            wav = is_d / f"s{bi:02d}_{pi:02d}.wav"
            kel_yol = wav.with_suffix(".json")
            if not wav.exists() or not kel_yol.exists() or json.loads(kel_yol.read_text()).get("metin") != p["metin"]:
                _, kel = video.seslendir(p["metin"], is_d, wav.stem, ses=SES,
                                         hiz="-4%" if uzun else "+4%", perde="-2Hz")
                kel_yol.write_text(json.dumps({"metin": p["metin"], "kelimeler": kel}, ensure_ascii=False))
            kel = noktala(p["metin"], json.loads(kel_yol.read_text())["kelimeler"])
            ses = wav_oku(wav)
            p.update(bas=t, sure=len(ses) / SR, ses=ses, kelimeler=[(t + a, t + b_, m) for a, b_, m in kel], bolum=bi)
            parcalar.append(p)
            t += p["sure"] + (PARCA_ARASI if uzun else 0.25)
    toplam = t + (2.0 if uzun else 1.2)
    n = int(toplam * SR)
    print(f"{kid}/{ad}: süre {toplam:.1f} sn, {len(parcalar)} parça", flush=True)

    # 2) ses karışımı
    konusma = np.zeros(n, dtype=np.float32)
    maske = np.zeros(n, dtype=bool)
    for p in parcalar:
        b = int(p["bas"] * SR)
        konusma[b:b + len(p["ses"])] += p["ses"]
        maske[b:b + len(p["ses"])] = True
    muzik = ortam_muzigi(n, tohum=sum(map(ord, kid + ad)))
    k = int(0.4 * SR)
    kazanc = np.convolve(np.where(maske, 0.35, 1.0), np.ones(k) / k, mode="same").astype(np.float32)
    karisim = konusma + muzik * kazanc
    karisim[-int(1.5 * SR):] *= np.linspace(1, 0, int(1.5 * SR))
    karisim = np.clip(karisim / max(1e-6, np.abs(karisim).max()) * 0.89, -1, 1)
    with wave.open(str(is_d / "ses.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes((karisim * 32767).astype(np.int16).tobytes())

    # 3) görsel planı: her parçanın süresi görselleri arasında bölünür
    sahneler = []
    for p in parcalar:
        g = p.get("gorsel") or [0]
        bas = 0.0 if p is parcalar[0] else p["bas"] - PARCA_ARASI / 2
        son = p["bas"] + p["sure"] + PARCA_ARASI / 2
        if p.get("grafik"):  # özgün grafik parçanın tamamını kaplar
            sahneler.append({"grafik": p["grafik"], "bas": bas, "son": son})
            continue
        for i, gi in enumerate(g):
            sahneler.append({"gorsel": gi, "bas": bas + (son - bas) * i / len(g), "son": bas + (son - bas) * (i + 1) / len(g)})
    sahneler[-1]["son"] = toplam
    for i in range(len(sahneler) - 1):
        sahneler[i]["son"] = sahneler[i + 1]["bas"]
    onbellek = {}

    def tuval(gi):
        if gi not in onbellek:
            onbellek[gi] = hazirla(dosya[gi], EN, BOY)
            if len(onbellek) > 6:
                onbellek.pop(next(iter(onbellek)))
        return onbellek[gi]

    def kredi(sc):
        if "grafik" in sc:
            return grafik.kredi(sc["grafik"])
        g = gorseller[sc["gorsel"]]
        return f"Görsel: {temiz(g['yazar'])[:38]} · {g['lisans']} · Wikimedia Commons"

    def kare_al(si, t):
        sc = sahneler[si]
        u = max(0.0, min(1.0, (t - sc["bas"]) / max(0.01, sc["son"] - sc["bas"])))
        if "grafik" in sc:
            return grafik.ciz(sc["grafik"], u, EN, BOY, koordinat)
        im = tuval(sc["gorsel"])
        yon = si % 4
        z = 1.0 + 0.10 * (u if yon in (0, 2) else 1 - u)
        ch = im.height / z
        cw = ch * EN / BOY
        if cw > im.width:
            cw, ch = im.width, im.width * BOY / EN
        pay = 0.35 if im.width / im.height < EN / BOY * 1.3 else 0.9  # geniş tuvalde baştan sona gezin
        mx = max(0.0, (im.width - cw) * (0.5 + (pay * (u - 0.5) if yon in (1, 2) else -pay * (u - 0.5))))
        my = max(0.0, (im.height - ch) / 2)
        return im.resize((EN, BOY), Image.BILINEAR, box=(mx, my, mx + cw, my + ch))

    gruplar = []
    en_cok = 7 if uzun else 3
    for p in parcalar:
        akt = []
        for w_ in p["kelimeler"]:
            akt.append(w_)
            if len(akt) >= en_cok or w_[2].endswith((".", "?", "!", ":")):
                gruplar.append(akt)
                akt = []
        if akt:
            gruplar.append(akt)
    if uzun:
        alt_f, bolum_f, bolum_k, buyuk_f, kredi_f = font(46), font(72), font(34, 600), font(120), font(22, 500)
        alt_y, alt_gen = BOY - 170, EN * 0.7
    else:
        alt_f, buyuk_f, kredi_f, baslik_f = font(66), font(110), font(24, 500), font(78)
        alt_y, alt_gen = BOY * 0.66, EN * 0.86
    vinyet = Image.new("L", (EN, BOY), 0)
    vd = ImageDraw.Draw(vinyet)
    for i in range(60):
        vd.rectangle((i * EN / 240, i * BOY / 216, EN - i * EN / 240, BOY - i * BOY / 216),
                     outline=int(110 * (1 - i / 60)), width=8)
    vinyet = vinyet.filter(ImageFilter.GaussianBlur(40))
    siyah = Image.new("RGB", (EN, BOY), (0, 0, 0))

    mp4 = cikti / f"{kid}-{ad}.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{EN}x{BOY}",
                           "-r", str(FPS), "-i", "-", "-i", str(is_d / "ses.wav"), "-c:v", "libx264", "-preset", "medium",
                           "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
                           "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    si, gi_ = 0, 0
    for f in range(int(toplam * FPS)):
        t = f / FPS
        while si + 1 < len(sahneler) and sahneler[si + 1]["bas"] <= t:
            si += 1
        kare = kare_al(si, t)
        if si + 1 < len(sahneler) and sahneler[si]["son"] - t < GECIS:
            a = 1 - (sahneler[si]["son"] - t) / GECIS
            kare = Image.blend(kare, kare_al(si + 1, sahneler[si + 1]["bas"]), max(0.0, min(1.0, a)))
        kare = Image.composite(siyah, kare, vinyet)
        d = ImageDraw.Draw(kare, "RGBA")
        acilis = 0.8 if uzun else 0.25
        if t < acilis or t > toplam - 1.2:
            a = (1 - t / acilis) if t < acilis else (t - (toplam - 1.2)) / 1.2
            d.rectangle((0, 0, EN, BOY), fill=(0, 0, 0, int(255 * max(0, min(1, a)))))
        if uzun:
            for bi, b in enumerate(bolumler):
                if bi and b["bas"] - 0.9 <= t < b["bas"] + 2.6:
                    a = min(1, (t - b["bas"] + 0.9) / 0.5, (b["bas"] + 2.6 - t) / 0.5)
                    d.rectangle((90, 110, 100, 230), fill=(232, 168, 60, int(255 * a)))
                    d.text((125, 108), f"BÖLÜM {bi}", font=bolum_k, fill=(232, 168, 60, int(255 * a)))
                    d.text((125, 148), b["ad"].upper(), font=bolum_f, fill=(255, 255, 255, int(255 * a)),
                           stroke_width=3, stroke_fill=(0, 0, 0, int(200 * a)))
        elif t < 3.2:  # Shorts: ilk saniyelerde ekran başlığı
            a = min(1.0, (3.2 - t) / 0.4)
            for j, sat in enumerate(satirla(d, s["ekran_basligi"].upper(), baslik_f, EN * 0.86)[:3]):
                metin_kutu(d, (EN / 2, BOY * 0.16 + j * 100), sat, baslik_f, ortala=True,
                           dolgu=(255, 214, 80, int(255 * a)), kutu=(0, 0, 0, int(170 * a)), pay=22)
        for p in parcalar:
            if p.get("yazi") and not p.get("grafik") and p["bas"] + 0.2 <= t < p["bas"] + 3.4:
                a = min(1, (t - p["bas"] - 0.2) / 0.3, (p["bas"] + 3.4 - t) / 0.4)
                for j, sat in enumerate(satirla(d, p["yazi"].upper(), buyuk_f, EN * 0.9)[:2]):
                    w = d.textlength(sat, font=buyuk_f)
                    d.text(((EN - w) / 2, BOY * (0.32 if uzun else 0.36) + j * buyuk_f.size * 1.1), sat,
                           font=buyuk_f, fill=(255, 255, 255, int(255 * a)), stroke_width=6,
                           stroke_fill=(0, 0, 0, int(220 * a)))
        while gi_ + 1 < len(gruplar) and gruplar[gi_ + 1][0][0] <= t:
            gi_ += 1
        g = gruplar[gi_]
        if g[0][0] - 0.1 <= t <= g[-1][1] + 0.5:
            metin = " ".join(w_[2] for w_ in g)
            for j, sat in enumerate(satirla(d, metin, alt_f, alt_gen)[-2:]):
                metin_kutu(d, (EN / 2, alt_y + j * alt_f.size * 1.35), sat, alt_f, ortala=True, kutu=(0, 0, 0, 140))
        kr = kredi(sahneler[si])
        d.text((EN - 30 * olc - d.textlength(kr, font=kredi_f), BOY - (40 if uzun else 70)), kr,
               font=kredi_f, fill=(255, 255, 255, 170))
        ff.stdin.write(kare.tobytes())
        if f % (FPS * 60) == 0:
            print(f"  {t / 60:.1f}/{toplam / 60:.1f} dk", flush=True)
    ff.stdin.close()
    if ff.wait():
        raise RuntimeError("ffmpeg hatası")

    # 4) açıklama: giriş + bölüm zamanları + kaynaklar + görsel lisansları (5000 karakter sınırı)
    kullanilan = sorted({sc["gorsel"] for sc in sahneler if "gorsel" in sc})
    sat = [s.get("aciklama", "").strip(), ""]
    if uzun:
        sat += ["Bölümler:", "0:00 Giriş"] + [f"{zs(b['bas'] - 0.9)} {b['ad']}" for b in bolumler[1:]] + [""]
    sat += ["Kaynaklar:"] + s.get("kaynaklar", []) + ["", "Görseller (Wikimedia Commons, özgün lisanslarıyla):"]
    sayac = {}
    for gi in kullanilan:  # aynı yazar+lisans tek satır
        anahtar = (temiz(gorseller[gi]["yazar"])[:40], gorseller[gi]["lisans"])
        sayac[anahtar] = sayac.get(anahtar, 0) + 1
    for (yazar, lisans), adet in sayac.items():
        sat.append(f"- {yazar} ({lisans})" + (f" · {adet} görsel" if adet > 1 else ""))
    sat += [f"Tüm görsel bağlantıları: {DEPO_URL}/{kid}/KAYNAKLAR.md", "",
            "Bu video CC BY-SA 4.0 lisansıyla paylaşılmıştır. Seslendirme yapay zekâ ile üretilmiştir.",
            "Bilgiler Wikipedia'dan derlenmiştir; hata görürseniz yorumda belirtin."]
    aciklama = "\n".join(sat)
    if len(aciklama) > 4800:  # görsel listesi uzunsa kısalt; bağlantılı tam liste depoda
        bas = sat.index("Görseller (Wikimedia Commons, özgün lisanslarıyla):")
        son = next(i for i, x in enumerate(sat) if x.startswith("Tüm görsel"))
        sat = sat[:bas + 1] + [f"({son - bas - 1} görsel; yazar ve lisanslar videoda ve bağlantıda)"] + sat[son:]
        aciklama = "\n".join(sat)
    (cikti / f"{kid}-{ad}.aciklama.txt").write_text(aciklama)
    kredi_md = [f"# {s['baslik']}", "", "## Kaynaklar", *[f"- {u}" for u in s.get("kaynaklar", [])], "",
                "## Görseller", *[f"- [{gorseller[gi]['baslik'][5:]}]({gorseller[gi]['sayfa']}) — "
                                  f"{temiz(gorseller[gi]['yazar'])}, {gorseller[gi]['lisans']}" for gi in kullanilan]]
    eski = (d_konu / "KAYNAKLAR.md").read_text() if (d_konu / "KAYNAKLAR.md").exists() else ""
    if s["baslik"] not in eski:
        (d_konu / "KAYNAKLAR.md").write_text((eski + "\n\n" if eski else "") + "\n".join(kredi_md) + "\n")

    sonuc = {"video": str(mp4), "aciklama": aciklama, "sure": toplam, "profil": "uzun" if uzun else "shorts"}
    if uzun:  # 5) kapak
        kapak = hazirla(dosya.get(s["kapak_gorsel"], dosya[yedek[0]]), 1280, 720, 1.0)
        kapak = Image.blend(kapak, Image.new("RGB", kapak.size, (0, 0, 0)), 0.25)
        d = ImageDraw.Draw(kapak)
        kf = font(96, 900)
        satirlar = satirla(d, s["kapak_yazisi"].upper(), kf, 1150)[:3]
        for j, st in enumerate(satirlar):
            w = d.textlength(st, font=kf)
            d.text(((1280 - w) / 2, 470 + j * 100 - 50 * (len(satirlar) - 1)), st, font=kf,
                   fill=(255, 214, 80), stroke_width=8, stroke_fill="black")
        kapak_yolu = cikti / f"{kid}-{ad}.kapak.jpg"
        kapak.save(kapak_yolu, quality=88)
        sonuc["kapak"] = str(kapak_yolu)
    return sonuc


if __name__ == "__main__":
    print(json.dumps(uret(sys.argv[1], sys.argv[2]), ensure_ascii=False)[:300])
