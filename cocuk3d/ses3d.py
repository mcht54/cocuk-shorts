"""3D bölümler için ses: karakter başına seslendirme, ağız hareketi zarfı, müzik
(konuşma altında kısılan), kodla üretilen efektler ve son karışım.

Tüm efekt ve müzik kodla sentezlenir (telif yok). Konuşma her zaman müziğin
ve efektlerin üstünde kalır; ölçüm kalite kontrolüne verilir.
"""
import math
import wave

import numpy as np

from cocuk import video

SR = video.SR


def satir_seslendir(metin, ses_profili, klasor, ad):
    orn, kel = video.seslendir(metin, klasor, ad, ses=ses_profili["ses"],
                               hiz=ses_profili.get("hiz", "+0%"), perde=ses_profili.get("perde", "+0Hz"))
    kel = video._noktalama_koru(metin, kel)
    return np.asarray(orn, dtype=np.float32) / 32768.0, kel


def zarf(sinyal, fps, toplam_kare):
    """Kare başına 0-1 konuşma şiddeti (ağız açıklığı için)."""
    pencere = SR // fps
    z = np.zeros(toplam_kare, dtype=np.float32)
    for f in range(toplam_kare):
        p = sinyal[f * pencere:(f + 1) * pencere]
        if len(p):
            z[f] = float(np.sqrt(np.mean(p * p)))
    tepe = np.percentile(z[z > 0], 95) if np.any(z > 0) else 1.0
    z = np.clip(z / max(tepe, 1e-4), 0, 1)
    z[z < 0.08] = 0
    # bir kare gecikmesiz yumuşatma
    return np.maximum(z, np.concatenate([[0], z[:-1]]) * 0.6)


def _nota(f, sure, zayif=3.2):
    t = np.arange(int(sure * SR)) / SR
    return np.exp(-zayif * t) * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t))


def muzik(n, tohum, sakin=False, macera=False):
    """Müzik kutusu + yumuşak bas; telifsiz, kodla. macera=True: hızlı tempo, minör akorlar, davul."""
    if macera:
        return _macera_muzigi(n, tohum)
    r = np.random.default_rng(tohum)
    buf = np.zeros(n, dtype=np.float32)
    kok = int(r.choice([60, 62, 65, 67]))
    akorlar = [[0, 4, 7, 12], [-3, 0, 4, 9], [5, 9, 12, 17], [7, 11, 14, 19]]
    vurus = 60 / float(r.choice([84, 92, 100])) / (1 if sakin else 2)
    t, i = 0.0, 0
    while t < n / SR:
        akor = akorlar[(i // 8) % 4]
        nota = kok + akor[int(r.integers(0, 4))]
        s = _nota(440 * 2 ** ((nota - 69) / 12), 1.4) * 0.18
        if i % 8 == 0:  # bas
            s2 = _nota(440 * 2 ** ((kok + akor[0] - 12 - 69) / 12), 2.0, 1.6) * 0.14
            b = int(t * SR)
            buf[b:b + len(s2)] += s2[:max(0, n - b)]
        b = int(t * SR)
        buf[b:b + len(s)] += s[:max(0, n - b)]
        t += vurus
        i += 1
    return buf


def _macera_muzigi(n, tohum):
    r = np.random.default_rng(tohum)
    buf = np.zeros(n, dtype=np.float32)
    kok = int(r.choice([57, 60, 62]))
    akorlar = [[0, 3, 7, 12], [-4, 0, 3, 8], [-2, 2, 5, 10], [-5, -1, 2, 7]]  # i - VI - VII - V
    vurus = 60 / float(r.choice([126, 132, 138])) / 2
    t, i = 0.0, 0
    while t < n / SR:
        b = int(t * SR)
        akor = akorlar[(i // 8) % 4]
        nota = kok + akor[(i * 3 + int(r.integers(0, 2))) % 4]  # arpej: ileri atılan hareket hissi
        s = _nota(440 * 2 ** ((nota - 69) / 12), 0.5, 7) * 0.13
        buf[b:b + len(s)] += s[:max(0, n - b)]
        if i % 2 == 0:  # davul: alçak "tum"
            tt = np.arange(int(0.18 * SR)) / SR
            dv = 0.22 * np.exp(-22 * tt) * np.sin(2 * np.pi * (95 - 50 * tt / 0.18) * tt)
            buf[b:b + len(dv)] += dv[:max(0, n - b)]
        if i % 8 == 0:
            s2 = _nota(440 * 2 ** ((kok + akor[0] - 12 - 69) / 12), 1.6, 1.8) * 0.12
            buf[b:b + len(s2)] += s2[:max(0, n - b)]
        t += vurus
        i += 1
    return buf


def efekt(tur, sure=0.35):
    t = np.arange(int(sure * SR)) / SR
    if tur == "zipla":  # yükselen "boing"
        f = 220 + 520 * (t / sure)
        return 0.35 * np.exp(-5 * t) * np.sin(2 * np.pi * np.cumsum(f) / SR)
    if tur == "adim":  # yumuşak pıt
        t = t[: int(0.06 * SR)]
        return 0.12 * np.exp(-60 * t) * np.sin(2 * np.pi * 140 * t)
    if tur == "pop":  # alma/verme
        t = t[: int(0.12 * SR)]
        return 0.28 * np.exp(-30 * t) * np.sin(2 * np.pi * (600 + 900 * t / 0.12) * t)
    if tur == "vin":  # hızlı hareket/atlayış "vınn"ı: süzülen gürültü
        t = t[: int(0.3 * SR)]
        g = np.random.default_rng(3).standard_normal(len(t))
        g = np.convolve(g, np.ones(12) / 12, mode="same")
        return 0.25 * np.sin(np.pi * t / t[-1]) * g
    if tur == "hazine":  # sandık açılınca: yükselen parlak akor
        out = np.zeros(int(1.0 * SR))
        for k, f in enumerate((523, 659, 784, 1047)):
            s = _nota(f, 0.8, 3) * 0.09
            b = int(k * 0.09 * SR)
            out[b:b + len(s)] += s[: len(out) - b]
        return out
    if tur == "parilti":
        out = np.zeros(int(0.6 * SR))
        for k, f in enumerate((1568, 2093, 2637)):
            s = _nota(f, 0.4, 7) * 0.08
            b = int(k * 0.07 * SR)
            out[b:b + len(s)] += s[: len(out) - b]
        return out
    raise ValueError(tur)


def karistir(konusma, muzik_izi, efekt_izi, konusma_maskesi):
    """Konuşma varken müziği ~-14 dB kıs (ducking), sonra tepe sınırla."""
    n = len(konusma)
    kazanc = np.where(konusma_maskesi, 0.2, 1.0).astype(np.float32)
    # 150 ms yumuşak geçiş
    k = int(0.15 * SR)
    if k > 1:
        kazanc = np.convolve(kazanc, np.ones(k) / k, mode="same")
    m = muzik_izi[:n] * kazanc * 0.55
    son = np.ones(n, dtype=np.float32)
    kapanis = int(1.2 * SR)
    son[-kapanis:] = np.linspace(1, 0, kapanis)
    toplam = konusma + m * son + efekt_izi[:n] * 0.8
    tepe = float(np.max(np.abs(toplam))) or 1.0
    toplam *= min(1.0, 0.89 / tepe)  # ≈ -1 dBFS
    return toplam, m * son


def konusma_muzik_farki_db(konusma, muzik_son, maske):
    """Konuşma bölümlerinde konuşma ile müziğin RMS farkı (dB). Kalite: >= 10 dB."""
    if not np.any(maske):
        return None
    k = np.sqrt(np.mean(konusma[maske] ** 2)) + 1e-9
    m = np.sqrt(np.mean(muzik_son[maske] ** 2)) + 1e-9
    return round(20 * math.log10(k / m), 1)


def wav_yaz(yol, sinyal):
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(sinyal, -1, 1) * 32767).astype("<i2").tobytes())
