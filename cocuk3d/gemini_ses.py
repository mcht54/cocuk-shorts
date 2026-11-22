"""Fındık ile Pamuk için doğal (Gemini) Türkçe sesler — kalıcı ses kütüphanesi.

Neden ayrı ve önceden: Gemini ücretsiz ses kotası küçüktür (günde ~10 istek) ve Dijital Çırak hattıyla aynı kotayı
paylaşabilir; o hattın sesi başka yedeği yoktur. Bu yüzden:
  * Sesler render sırasında DEĞİL, gece penceresinde (TR 22:00–10:30, kota ~11:00'de sıfırlanır; Dijital Çırak üretimi
    16:30/21:00'de biter) otonom/ses_hazirla.py ile sıradaki bölümler için üretilir ve ses_kutuphane/ altına işlenir.
  * Render (planla) yalnız kütüphaneden okur; bölümün TÜM Türkçe satırları kütüphanedeyse Gemini sesi, değilse bölümün
    tamamı eski edge-tts sesiyle (aynı bölümde iki farklı ses karışmaz). Üretim hiçbir durumda durmaz.
  * İngilizce ders satırları (dil: en) her zaman edge en-US sesiyle kalır.

Bölüm başına çağrı: en çok konuşan iki kişi tek çok-konuşmacılı çağrıda, kalan kişi (genelde anlatıcı) tek çağrıda;
whisper ile satır sınırları bulunur, tutmayan satır tek başına yeniden seslendirilir. Bir satır bile tutmazsa bölüm
kütüphaneye hiç yazılmaz (yarım bölüm olmaz).
"""
import base64
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent.parent
KUTUPHANE = KOK / "ses_kutuphane"
SR = 24000
SURUM = "g1"
API = "https://generativelanguage.googleapis.com/v1beta"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TR = dt.timezone(dt.timedelta(hours=3))

# Ses ve üslup (seri.json'da "gemini" ile değiştirilebilir). perde: 1.0 = değişmez; çocuk karakterler biraz inceltilir.
VARSAYILAN = {
    "findik": {"ses": "Puck", "perde": 1.12,
               "tarz": "Meraklı, enerjik, neşeli küçük bir çocuk gibi; sıcak, gülümseyen, doğal bir sesle konuş."},
    "pamuk": {"ses": "Leda", "perde": 1.08,
              "tarz": "Yumuşak kalpli, biraz utangaç, tatlı küçük bir çocuk gibi; nazik ve doğal konuş."},
    "anlatici": {"ses": "Algieba", "perde": 1.0,
                 "tarz": "Çocuklara masal anlatan sıcak, sakin, gülümseyen bir anlatıcı gibi; acele etmeden, canlı vurgularla oku."},
}
DIYALOG_TARZ = ("Bu, 3-7 yaş çocuklar için Türkçe bir çizgi film diyaloğu. Karakterler sevimli, neşeli ve doğal konuşsun; "
                "duyguyu (şaşırma, sevinç, merak) sesle göster, ama metni aynen oku, hiçbir şey ekleme.")


class KotaBitti(RuntimeError):
    pass


def penceride(simdi=None):
    """Gemini ses üretimine izin verilen saat mi (TR 22:00–10:30)."""
    s = (simdi or dt.datetime.now(TR)).astimezone(TR)
    return s.hour >= 22 or s.hour < 10 or (s.hour == 10 and s.minute < 30)


def sesler(seri):
    return {k: {**v, **(seri.get("gemini", {}).get(k, {}))} for k, v in VARSAYILAN.items()}


def anahtar(kim, metin, ayar):
    a = ayar.get(kim, {})
    return hashlib.md5(f"{SURUM}|{kim}|{a.get('ses')}|{a.get('perde')}|{metin}".encode()).hexdigest()[:16]


# ---------- kütüphaneden okuma (render tarafı: ağ yok, whisper yok) ----------

def _oku(k, klasor):
    ogg, js = klasor / f"{k}.ogg", klasor / f"{k}.json"
    if not (ogg.exists() and js.exists()):
        return None
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ogg), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True, check=True)
    sinyal = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return sinyal, [tuple(x) for x in json.loads(js.read_text())["kel"]]


def _dizin(klasor):
    yol = klasor / "dizin.json"
    return json.loads(yol.read_text()) if yol.exists() else {}


def _tok(m):
    return [norm(t) for t in m.split() if norm(t)]


def al(kim, metin, ayar, klasor=KUTUPHANE):
    """(sinyal float32 24 kHz, kel [(bas, son, kelime)]) ya da None. Tam metin yoksa, metin kütüphanedeki bir satırın
    ardışık bir parçasıysa (uzun derlemede "Yarın devam!" atılınca) ses kelime zamanlarından kesilir."""
    try:
        v = _oku(anahtar(kim, metin, ayar), klasor)
        if v:
            return v
        hedef = _tok(metin)
        if not hedef:
            return None
        for k, d in _dizin(klasor).items():
            if d.get("kim") != kim or d.get("ses") != ayar.get(kim, {}).get("ses"):
                continue
            kaynak = _tok(d["metin"])
            for i in range(len(kaynak) - len(hedef) + 1):
                if kaynak[i:i + len(hedef)] == hedef:
                    v = _oku(k, klasor)
                    if not v:
                        break
                    sinyal, kel = v
                    kel = [x for x in kel if norm(x[2])]
                    if len(kel) != len(kaynak):
                        break
                    a = max(0.0, kel[i][0] - 0.08)
                    b = min(len(sinyal) / SR, kel[i + len(hedef) - 1][1] + 0.3)
                    jet = metin.split()
                    yeni = [(round(x[0] - a, 3), round(x[1] - a, 3), jet[j] if j < len(jet) else x[2])
                            for j, x in enumerate(kel[i:i + len(hedef)])]
                    return sinyal[int(a * SR):int(b * SR)].copy(), _nokta(yeni)
    except Exception as e:  # noqa: BLE001 — kütüphane okunamazsa edge sesi kullanılır
        print("ses kütüphanesi okunamadı:", str(e)[:150], flush=True)
    return None


def bolum_sesleri(satirlar, ayar, klasor=KUTUPHANE):
    """satirlar: [(kim, metin)] (yalnız Türkçe). Hepsi kütüphanedeyse {(kim, metin): (sinyal, kel)}, değilse None."""
    out = {}
    for kim, metin in satirlar:
        if (kim, metin) in out:
            continue
        if kim not in ayar:
            return None
        v = al(kim, metin, ayar, klasor)
        if v is None:
            return None
        out[(kim, metin)] = v
    return out


# ---------- üretim (yalnız otonom/ses_hazirla.py; ağ + whisper) ----------

def norm(s):
    return re.sub(r"[^a-zçğıöşüâî0-9]", "", s.replace("I", "ı").replace("İ", "i").lower())


def _nokta(kel):
    if kel:
        a, b, t = kel[-1]
        kel[-1] = (a, b, t if t[-1:] in ".!?…" else t + ".")
    return kel


def _istek(govde, zaman=180):
    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        raise KotaBitti("GEMINI_API_KEY yok")
    req = urllib.request.Request(f"{API}/models/{TTS_MODEL}:generateContent", data=json.dumps(govde).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": k})
    with urllib.request.urlopen(req, timeout=zaman) as r:
        return json.load(r)


class Sayac:
    """Bir çalışmadaki Gemini ses isteği bütçesi (kotayı Dijital Çırak'tan yememek için sınırlı)."""

    def __init__(self, butce):
        self.kalan = butce

    def cagir(self, govde):
        if self.kalan <= 0:
            raise KotaBitti("bu çalışmanın ses bütçesi bitti")
        for i in range(2):
            self.kalan -= 1
            try:
                r = _istek(govde)
                return base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            except urllib.error.HTTPError as e:
                h = e.read().decode()[:300]
                print("gemini ses:", e.code, h[:200], flush=True)
                if e.code == 429:  # dakikalık ya da günlük: kotayı zorlamadan dur (kalan bölümler sonraki gece)
                    raise KotaBitti(h[:120])
                if e.code not in (500, 503) or self.kalan <= 0:
                    raise
                time.sleep(30)
            except (KeyError, IndexError, ValueError, TimeoutError, urllib.error.URLError) as e:
                print("gemini ses:", repr(e)[:200], flush=True)
                if i or self.kalan <= 0:
                    raise
                time.sleep(10)
        raise RuntimeError("gemini ses yanıt vermedi")


def _tek(sayac, metin, a):
    return sayac.cagir({"contents": [{"parts": [{"text": f"{a['tarz']}\n{metin}"}]}],
                        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": a["ses"]}}}}})


def _ikili(sayac, satirlar, ayar):
    """satirlar: [(kim, metin)] en çok iki kişi."""
    adlar = list(dict.fromkeys(k for k, _ in satirlar))
    ad = {k: ("Findik" if k == "findik" else "Pamuk" if k == "pamuk" else "Anlatici") for k in adlar}
    tarz = DIYALOG_TARZ + " " + " ".join(f"{ad[k]}: {ayar[k]['tarz']}" for k in adlar)
    metin = tarz + "\n" + "\n".join(f"{ad[k]}: {m}" for k, m in satirlar)
    return sayac.cagir({"contents": [{"parts": [{"text": metin}]}],
                        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"multiSpeakerVoiceConfig": {
                            "speakerVoiceConfigs": [{"speaker": ad[k], "voiceConfig": {"prebuiltVoiceConfig": {
                                "voiceName": ayar[k]["ses"]}}} for k in adlar]}}}})


_model = None


def _whisper():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("small", compute_type="int8")
    return _model


def _dinle(sinyal):
    a16 = np.interp(np.arange(0, len(sinyal), SR / 16000), np.arange(len(sinyal)), sinyal).astype(np.float32)
    segs, _ = _whisper().transcribe(a16, language="tr", word_timestamps=True)
    return [w for s in segs for w in s.words]


SAYI_KELIME = ("bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz", "on", "yirmi", "otuz", "kırk", "elli",
               "altmış", "yetmiş", "seksen", "doksan", "yüz", "bin", "yarım", "buçuk")


def _sayi_mi(t, yazi):
    """Yazıyla sayı (ekli de: "üçüncü" hariç kısa ekler) ya da whisper'ın rakamla yazdığı ("3", "5'e")."""
    if not yazi and re.search(r"\d", t):
        return True
    n = norm(t)
    return any(n == w or (len(w) >= 3 and n.startswith(w) and len(n) - len(w) <= 3) for w in SAYI_KELIME)


def _sayisiz(tokenler, yazi):
    out = []
    for t in tokenler:
        if _sayi_mi(t, yazi):
            if not out or out[-1] != "#":
                out.append("#")
        elif norm(t):
            out.append(norm(t))
    return "".join(out)


def benzerlik(metin, ww):
    return difflib.SequenceMatcher(None, _sayisiz(metin.split(), True), _sayisiz([w.word for w in ww], False)).ratio()


def _hizala(metin, ww, sure):
    toks = metin.split()
    zt = [None] * len(toks)
    sm = difflib.SequenceMatcher(None, [norm(t) for t in toks], [norm(w.word) for w in ww])
    for blk in sm.get_matching_blocks():
        for i in range(blk.size):
            zt[blk.a + i] = (ww[blk.b + i].start, ww[blk.b + i].end)
    bas = ww[0].start if ww else 0.05
    son = ww[-1].end if ww else sure - 0.25
    i = 0
    while i < len(toks):
        if zt[i] is None:
            j = i
            while j < len(toks) and zt[j] is None:
                j += 1
            a0 = zt[i - 1][1] if i else bas
            b0 = zt[j][0] if j < len(toks) else son
            for q in range(i, j):
                zt[q] = (a0 + (b0 - a0) * (q - i) / (j - i), a0 + (b0 - a0) * (q - i + 1) / (j - i))
            i = j
        else:
            i += 1
    return _nokta([(round(x, 3), round(y, 3), t) for (x, y), t in zip(zt, toks)])


def _ffmpeg(sinyal, filtre):
    with tempfile.TemporaryDirectory() as d:
        g, c = Path(d) / "g.raw", Path(d) / "c.raw"
        (np.clip(sinyal, -1, 1) * 32767).astype(np.int16).tofile(g)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", str(g), "-af", filtre,
                        "-f", "s16le", "-ar", str(SR), "-ac", "1", str(c)], check=True)
        return np.fromfile(c, dtype=np.int16).astype(np.float32) / 32768.0


def _son_hal(sinyal, perde):
    """Baş/son sessizliği kırpar, perdeyi (süreyi bozmadan) ayarlar, 60 ms baş + 0.25 sn kuyruk bırakır."""
    f = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse")
    if abs(perde - 1.0) > 1e-3:
        f += f",asetrate={int(SR * perde)},aresample={SR},atempo={1 / perde:.5f}"
    f += ",adelay=60,apad=pad_dur=0.25"
    return _ffmpeg(sinyal, f)


def _pcm(b):
    return np.frombuffer(b, dtype=np.int16).astype(np.float32) / 32768.0


def _bol(grup, sinyal):
    """Tek sesteki ardışık satırları whisper ile böler. Döner: [ham parça ya da None (bulunamadı)]."""
    ww = _dinle(sinyal)
    toks = [(i, t) for i, (_, m) in enumerate(grup) for t in m.split()]
    zt = [None] * len(toks)
    sm = difflib.SequenceMatcher(None, [norm(t) for _, t in toks], [norm(w.word) for w in ww])
    for blk in sm.get_matching_blocks():
        for i in range(blk.size):
            zt[blk.a + i] = (ww[blk.b + i].start, ww[blk.b + i].end)
    sinir = {}
    for i in range(len(grup)):
        idx = [j for j, (ii, _) in enumerate(toks) if ii == i and zt[j]]
        sinir[i] = (zt[idx[0]][0], zt[idx[-1]][1]) if idx else None
    sure = len(sinyal) / SR
    out = []
    for i in range(len(grup)):
        if sinir[i] is None:
            out.append(None)
            continue
        onceki = next((sinir[j] for j in range(i - 1, -1, -1) if sinir[j]), None)
        sonraki = next((sinir[j] for j in range(i + 1, len(grup)) if sinir[j]), None)
        bas = 0.0 if onceki is None else (onceki[1] + sinir[i][0]) / 2
        son = sure if sonraki is None else (sinir[i][1] + sonraki[0]) / 2
        bas, son = max(0.0, bas - 0.05), min(sure, son + 0.08)
        out.append(sinyal[int(bas * SR):int(son * SR)])
    return out


def _gruplar(satirlar):
    say = {}
    for k, _ in satirlar:
        say[k] = say.get(k, 0) + 1
    ana = sorted(say, key=lambda k: -say[k])[:2]
    gr = [[s for s in satirlar if s[0] in ana]]
    for k in say:
        if k not in ana:
            gr.append([s for s in satirlar if s[0] == k])
    return gr


def _kaydet(klasor, k, kim, metin, sinyal, kel, rapor):
    klasor.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        g = Path(d) / "g.raw"
        (np.clip(sinyal, -1, 1) * 32767).astype(np.int16).tofile(g)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", str(g),
                        "-c:a", "libopus", "-b:a", "48k", str(klasor / f"{k}.ogg")], check=True)
    (klasor / f"{k}.json").write_text(json.dumps({"kim": kim, "metin": metin, "kel": kel, **rapor}, ensure_ascii=False))


def hazirla(satirlar, ayar, sayac, klasor=KUTUPHANE, esik=0.72):
    """Bir bölümün Türkçe satırlarını ([(kim, metin)]) seslendirip kütüphaneye yazar. Hepsi tutarsa True.
    Kota/bütçe biterse KotaBitti fırlar. Tutan satırlar yazılır; render yine yalnız bölüm TAMAMSA kütüphaneyi kullanır."""
    satirlar = list(dict.fromkeys(s for s in satirlar if s[0] in ayar))
    eksik = [s for s in satirlar if al(s[0], s[1], ayar, klasor) is None]
    if not eksik:
        return True
    for gi, grup in enumerate(_gruplar(eksik)):
        adlar = {k for k, _ in grup}
        if gi:
            time.sleep(22)  # ücretsiz katman dakikalık sınır
        try:
            if len(adlar) == 2:
                ham = _pcm(_ikili(sayac, grup, ayar))
            else:
                a = ayar[next(iter(adlar))]
                ham = _pcm(_tek(sayac, "\n".join(m for _, m in grup), a))
            parcalar = _bol(grup, ham)
        except KotaBitti:
            raise
        except Exception as e:  # noqa: BLE001
            print("grup sesi üretilemedi:", str(e)[:200], "→ satırlar tek tek", flush=True)
            parcalar = [None] * len(grup)
        for (kim, metin), p in zip(grup, parcalar):
            for deneme in range(3):
                if p is None:
                    time.sleep(22)
                    p = _pcm(_tek(sayac, metin, ayar[kim]))
                son = _son_hal(p, float(ayar[kim].get("perde", 1.0)))
                ww = _dinle(son)
                b = benzerlik(metin, ww)
                print(f"ses {kim}: {len(son) / SR:.1f} sn benzerlik {b:.2f} | {' '.join(w.word.strip() for w in ww)}", flush=True)
                if b >= esik:  # tutan satır hemen yazılır: kota yarıda biterse sonraki gece yalnız eksikler üretilir
                    _yaz(klasor, kim, metin, son, _hizala(metin, ww, len(son) / SR), round(b, 2), ayar)
                    break
                p = None
            else:
                print(f"satır tutmadı (bölüm edge-tts ile çizilecek, sonraki gece yeniden denenir): {kim}: {metin[:60]}", flush=True)
                return False
    return True


def _yaz(klasor, kim, metin, son, kel, b, ayar):
    k = anahtar(kim, metin, ayar)
    _kaydet(klasor, k, kim, metin, son, kel, {"benzerlik": b, "ses": ayar[kim]["ses"], "model": TTS_MODEL})
    dizin = _dizin(klasor)
    dizin[k] = {"kim": kim, "metin": metin, "ses": ayar[kim]["ses"]}
    (klasor / "dizin.json").write_text(json.dumps(dizin, ensure_ascii=False, indent=0))
