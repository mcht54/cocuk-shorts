"""Bölüm dosyası -> kare kare çekim planı (Blender için) + ses + kurgu bilgisi.

Çıktılar (is_dizini altında):
  plan.json   Blender'ın uygulayacağı her şey (karakter pozları, nesne tutma, kamera, ışık)
  kurgu.json  altyazı kelimeleri, başlık, çekim sınırları, ses ölçümleri
  ses.wav     son karışım
Seslendirmeler is_dizini/ses altında önbelleklenir (kaldığı yerden devam).
"""
import hashlib
import json
from pathlib import Path

import numpy as np

from . import animasyon, kamera, ses3d
from .profil import profil as profil_al

SR = ses3d.SR
BASLANGIC_PAY = 0.35
SATIR_ARASI = 0.3
CEKIM_SONU = 0.45
EN_KISA_CEKIM = 2.0


def yukle(seri_dizini, bolum_yolu):
    seri = json.loads((Path(seri_dizini) / "seri.json").read_text())
    bolum = json.loads(Path(bolum_yolu).read_text())
    if bolum["seri_id"] != seri["seri_id"]:
        raise ValueError("bölüm başka bir seriye ait")
    for c in bolum["cekimler"]:
        for s in c.get("satirlar", []):
            if s["kim"] not in seri["karakterler"]:
                raise ValueError(f"tanımsız karakter: {s['kim']} (yeni karakter seri.json'a eklenmeli)")
        for e in c.get("eylemler", []):
            if e["kim"] not in seri["karakterler"]:
                raise ValueError(f"tanımsız karakter: {e['kim']}")
    return seri, bolum


def _yuvarla(o):
    if isinstance(o, float):
        return round(o, 4)
    if isinstance(o, list):
        return [_yuvarla(x) for x in o]
    if isinstance(o, dict):
        return {k: _yuvarla(v) for k, v in o.items()}
    return o


def planla(seri_dizini, bolum_yolu, profil_adi, is_dizini, prototip=False):
    seri, bolum = yukle(seri_dizini, bolum_yolu)
    prof = profil_al(profil_adi, prototip)
    fps, en, boy = prof["fps"], prof["en"], prof["boy"]
    sx = prof["x_sikistir"]
    is_dizini = Path(is_dizini)
    (is_dizini / "ses").mkdir(parents=True, exist_ok=True)

    kar_tanim = {k: v for k, v in seri["karakterler"].items() if v["tur"] != "ses"}
    cekimler = [dict(c) for c in bolum["cekimler"]]
    if prof["giris_cekimi"] and bolum.get("giris_cekimi", True):  # bölüm kapatabilir (ör. diyalogsuz test)
        cekimler.insert(0, {
            "id": "giris", "tip": "genis", "hareket": "donus", "isik": cekimler[0].get("isik", "sabah"),
            "hedef": list(bolum["baslangic"]),
            "satirlar": [{"kim": "anlatici",
                          "metin": f"{seri['seri_adi']}! Bölüm {bolum['bolum_no']}: {bolum['baslik']}."}],
            "eylemler": [{"kim": k, "eylem": "el_salla", "bas": 0.25, "son": 0.95} for k in bolum["baslangic"]],
        })

    # 1) seslendirme ve çekim süreleri
    zaman = 0.0
    satirlar, kelimeler = [], []
    for c in cekimler:
        t = BASLANGIC_PAY
        for i, s in enumerate(c.get("satirlar", [])):
            prof_ses = seri["karakterler"][s["kim"]]["ses"]
            anahtar = hashlib.md5((s["metin"] + json.dumps(prof_ses, sort_keys=True)).encode()).hexdigest()[:12]
            npy = is_dizini / "ses" / f"{anahtar}.npy"
            kj = is_dizini / "ses" / f"{anahtar}.json"
            if npy.exists() and kj.exists():
                sinyal, kel = np.load(npy), [tuple(x) for x in json.loads(kj.read_text())]
            else:
                sinyal, kel = ses3d.satir_seslendir(s["metin"], prof_ses, is_dizini / "ses", anahtar)
                np.save(npy, sinyal)
                kj.write_text(json.dumps(kel, ensure_ascii=False))
            bas = zaman + t
            satirlar.append({"kim": s["kim"], "bas": bas, "sinyal": sinyal, "metin": s["metin"], "cekim": c["id"]})
            kelimeler += [{"bas": bas + a, "son": bas + b, "metin": m, "kim": s["kim"]} for a, b, m in kel]
            t += len(sinyal) / SR + SATIR_ARASI
        sure = max(t - SATIR_ARASI + CEKIM_SONU, c.get("en_az", EN_KISA_CEKIM))
        kare = int(round(sure * fps))
        c["bas_kare"] = int(round(zaman * fps))
        c["kare_say"] = kare
        c["bas"], c["sure"] = c["bas_kare"] / fps, kare / fps
        zaman = (c["bas_kare"] + kare) / fps
    toplam_kare = cekimler[-1]["bas_kare"] + cekimler[-1]["kare_say"]
    toplam = toplam_kare / fps
    n = int(round(toplam * SR))

    # 2) eylemleri mutlak zamana çevir
    eylemler = []
    for c in cekimler:
        for e in c.get("eylemler", []):
            e2 = dict(e)
            e2["bas"] = c["bas"] + e["bas"] * c["sure"]
            e2["son"] = c["bas"] + e.get("son", e["bas"] + 0.01) * c["sure"]
            if "nereye" in e2:
                e2["nereye"] = [e2["nereye"][0] * sx, e2["nereye"][1]]
            eylemler.append(e2)

    # 3) konuşma izleri ve ağız zarfları
    konusma = np.zeros(n, dtype=np.float32)
    kisi_izi = {k: np.zeros(n, dtype=np.float32) for k in kar_tanim}
    maske = np.zeros(n, dtype=bool)
    for s in satirlar:
        b = int(s["bas"] * SR)
        sg = s["sinyal"][: max(0, n - b)]
        konusma[b:b + len(sg)] += sg
        maske[b:b + len(sg)] = True
        if s["kim"] in kisi_izi:
            kisi_izi[s["kim"]][b:b + len(sg)] += sg
    zarflar = {k: ses3d.zarf(v, fps, toplam_kare).tolist() for k, v in kisi_izi.items()}

    # 4) animasyon
    karakterler = {k: {"konum": [bolum["baslangic"][k][0] * sx, bolum["baslangic"][k][1]],
                       "boy": v.get("boy", 1.0), "tur": v["tur"]}
                   for k, v in kar_tanim.items() if k in bolum["baslangic"]}
    nesneler = {k: {"konum": [v[0] * sx, v[1], v[2]]} for k, v in bolum.get("nesne_yerlesim", {}).items()}
    pozlar, tutma = animasyon.hesapla(karakterler, eylemler, toplam, fps, zarflar, nesneler)

    # 5) kamera ve ışık
    boylar = {k: v["boy"] for k, v in karakterler.items()}
    kam, isik = [], []
    for c in cekimler:
        c["hedef"] = [h for h in c.get("hedef", list(karakterler)) if h in karakterler] or list(karakterler)
        kam += kamera.kamera_yolu(c, pozlar, boylar, c["bas_kare"], c["kare_say"], en, boy)
        isik += kamera.isik_yolu(c, c["kare_say"])

    # 6) efektler
    efekt_izi = np.zeros(n, dtype=np.float32)
    efektler = []

    def ekle(tur, t):
        s = ses3d.efekt(tur)
        b = int(t * SR)
        if b < n:
            efekt_izi[b:b + len(s)] += s[: n - b]
            efektler.append({"tur": tur, "t": round(t, 3)})

    for e in eylemler:
        if e["eylem"] == "zipla":
            kez = e.get("kez", 1)
            for j in range(kez):
                ekle("zipla", e["bas"] + (j + 0.18) / kez * (e["son"] - e["bas"]))
        elif e["eylem"] in ("yuru", "kos"):
            aralik = 0.2 if e["eylem"] == "kos" else 0.3
            t = e["bas"] + 0.1
            while t < e["son"] - 0.05:
                ekle("adim", t)
                t += aralik
        elif e["eylem"] == "tut":
            ekle("pop", e["bas"] + 0.45 * (e["son"] - e["bas"]))
        elif e["eylem"] == "ver":
            ekle("pop", e["bas"] + 0.5 * (e["son"] - e["bas"]))
            ekle("parilti", e["bas"] + 0.55 * (e["son"] - e["bas"]))

    tohum = int(hashlib.md5(bolum["baslik"].encode()).hexdigest()[:8], 16)
    muzik = ses3d.muzik(n, tohum)
    karisim, muzik_son = ses3d.karistir(konusma, muzik, efekt_izi, maske)
    ses3d.wav_yaz(is_dizini / "ses.wav", karisim)

    plan = {
        "profil": prof, "fps": fps, "en": en, "boy": boy, "kare_say": toplam_kare,
        "mekan": seri["mekanlar"][bolum["mekan"]],
        "karakterler": {k: dict(kar_tanim[k], id=k) for k in karakterler},
        "nesneler": {k: dict(seri["nesneler"][k], konum=v["konum"]) for k, v in nesneler.items()},
        "pozlar": pozlar, "tutma": tutma, "kamera": kam, "isik": isik,
        "cekimler": [{k: c[k] for k in ("id", "tip", "hareket", "hedef", "bas_kare", "kare_say")}
                     | {"isik": c.get("isik", "sabah"), "isik_son": c.get("isik_son", c.get("isik", "sabah")),
                        "eylemler": [e["eylem"] for e in c.get("eylemler", [])]}
                     for c in cekimler],
    }
    (is_dizini / "plan.json").write_text(json.dumps(_yuvarla(plan)))
    kurgu = {
        "profil": prof, "fps": fps, "kare_say": toplam_kare, "sure": toplam,
        "baslik": bolum.get("ekran_basligi", bolum["baslik"]),
        "kelimeler": _yuvarla(kelimeler),
        "satirlar": [{"kim": s["kim"], "bas": round(s["bas"], 3), "son": round(s["bas"] + len(s["sinyal"]) / SR, 3),
                      "cekim": s["cekim"]} for s in satirlar],
        "cekimler": plan["cekimler"],
        "efektler": efektler,
        "ses": {"ornek": n, "konusma_muzik_db": ses3d.konusma_muzik_farki_db(konusma, muzik_son, maske),
                "konusma_ornek": int(maske.sum())},
        "zarflar": _yuvarla(zarflar),
        "karakter_adlari": {k: v["ad"] for k, v in seri["karakterler"].items()},
    }
    (is_dizini / "kurgu.json").write_text(json.dumps(kurgu, ensure_ascii=False))
    return plan, kurgu
