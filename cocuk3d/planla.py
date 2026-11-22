"""Bölüm dosyası -> kare kare çekim planı (Blender için) + ses + kurgu bilgisi.

Çıktılar (is_dizini altında):
  plan.json   Blender'ın uygulayacağı her şey (karakter pozları, nesne tutma, kamera, ışık)
  kurgu.json  altyazı kelimeleri, başlık, çekim sınırları, ses ölçümleri
  ses.wav     son karışım
Seslendirmeler is_dizini/ses altında önbelleklenir (kaldığı yerden devam).
"""
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np

from . import animasyon, gemini_ses, kamera, ses3d
from .profil import profil as profil_al

SR = ses3d.SR
BASLANGIC_PAY = 0.35
SATIR_ARASI = 0.3
CEKIM_SONU = 0.45
EN_KISA_CEKIM = 2.0
KART_TUT = 1.6  # İngilizce kelime kartı satırdan sonra bu kadar ekranda kalır


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


def _sessizlik_kirp(sinyal, kel, pay=0.25):
    """Satır sonundaki sessizliği (son kelimeden ve son sesli örnekten sonra) pay saniyeye indirir."""
    sesli = np.where(np.abs(sinyal) > 0.02)[0]
    son = max(sesli[-1] / SR if len(sesli) else 0.0, kel[-1][1] if kel else 0.0)
    return sinyal[:min(len(sinyal), int((son + pay) * SR))]


def _yuvarla(o):
    if isinstance(o, float):
        return round(o, 4)
    if isinstance(o, list):
        return [_yuvarla(x) for x in o]
    if isinstance(o, dict):
        return {k: _yuvarla(v) for k, v in o.items()}
    return o


DEVAM_CUMLESI = re.compile(r"[^.!?…]*\b(yarın devam|cevap yarın|devamı yarın)[^.!?…]*[.!?…]*", re.I)


def devam_cumlelerini_at(cekimler):
    """Uzun derlemede sonraki bölüm hemen başladığı için "Yarın devam!" gibi seri cümleleri atılır;
    boş kalan satır da düşer."""
    for c in cekimler:
        satirlar = []
        for s in c.get("satirlar", []):
            metin = re.sub(r"\s{2,}", " ", DEVAM_CUMLESI.sub("", s["metin"])).strip()
            if metin:
                satirlar.append({**s, "metin": metin})
        if "satirlar" in c:
            c["satirlar"] = satirlar
    return cekimler


def cekim_listesi(seri, bolum, profil_adi, prototip=False):
    """Bölümün çekimleri; profile göre giriş çekimi eklenir, uzun derlemede seri cümleleri atılır."""
    prof = profil_al(profil_adi, prototip)
    cekimler = [dict(c) for c in bolum["cekimler"]]
    if profil_adi == "uzun":
        devam_cumlelerini_at(cekimler)
    if prof["giris_cekimi"] and bolum.get("giris_cekimi", True):  # bölüm kapatabilir (ör. diyalogsuz test)
        cekimler.insert(0, {
            "id": "giris", "tip": "genis", "hareket": "donus", "isik": cekimler[0].get("isik", "sabah"),
            "hedef": list(bolum["baslangic"]),
            "satirlar": [{"kim": "anlatici",
                          "metin": bolum.get("giris_metni")
                          or f"{seri['seri_adi']}! Bölüm {bolum['bolum_no']}: {bolum['baslik']}."}],
            "eylemler": [{"kim": k, "eylem": "el_salla", "bas": 0.25, "son": 0.95} for k in bolum["baslangic"]],
        })
    return cekimler


def turkce_satirlar(cekimler):
    return [(s["kim"], s["metin"]) for c in cekimler for s in c.get("satirlar", []) if s.get("dil", "tr") != "en"]


KESME_EN_KISA = 1.6   # sn: alt çekim bundan kısa olmaz
KESME_EN_UZUN = 4.2   # sn: konuşma olmasa da bundan uzun tek açı kalmaz (izlenme: 3-4 sn'de bir görüntü değişsin)
HAREKET = {"yuru", "kos", "atla"}  # bu sırada tek karaktere yakın plan yok (koşan karakter kadrajdan çıkar)
KESILEBILIR = {"ifade", "bak"}  # yüz ifadesi / bakış: kesme bunların ortasına düşebilir (ölçülen hareket değil)


EN_AZ_ARA = 0.45  # m (kadrajda): iki karakter yan yana bundan yakın durursa kamerada üst üste biner


def karakterleri_ayir(bolum, cekimler, sx):
    """Yazarın üst üste koyduğu karakterleri (ör. b052: 20 cm arayla aynı çizgide koşan ikili) ayırır: bir karakter
    öbürüne EN_AZ_ARA'dan yakın bir yere gidecekse, geldiği taraftaki yanına konur (kovalamacada arkada kalır).
    Bölüm dosyasına dokunmaz; kopyalar üzerinde çalışır. Döner: düzeltilmiş başlangıç konumları."""
    ara = EN_AZ_ARA / sx
    bas = {k: list(v) for k, v in bolum.get("baslangic", {}).items()}
    ks = list(bas)
    for i, a in enumerate(ks):  # başlangıç: soldan sağa sıralı aralık
        for b in ks[i + 1:]:
            if abs(bas[a][0] - bas[b][0]) < ara:
                yon = 1 if bas[b][0] >= bas[a][0] else -1
                bas[b][0] = bas[a][0] + yon * ara
    konum = {k: list(v) for k, v in bas.items()}
    for c in cekimler:
        c["eylemler"] = [dict(e) for e in c.get("eylemler", [])]
        for e in sorted(c["eylemler"], key=lambda e: e["bas"]):
            if "nereye" not in e or e["kim"] not in konum:
                continue
            hedef = list(e["nereye"])
            for o, p in konum.items():
                if o != e["kim"] and abs(hedef[0] - p[0]) < ara:
                    yon = -1 if konum[e["kim"]][0] < p[0] else 1  # geldiği taraf
                    hedef[0] = p[0] + yon * ara
            e["nereye"] = hedef
            konum[e["kim"]] = hedef
    return bas


def _kisa_yuruyusleri_isaretle(cekimler, bolum, sx, esik=0.3):
    """Yazarın 10-30 cm'lik "yürü"leri (ör. e016/e017) animasyonda adım olarak kalır, ama kalite denetimindeki
    "yürüme var ama yer değiştirmedi" ölçümüne girmez (yoksa bölüm iki kez kalıp atlanıyordu)."""
    konum = {k: [v[0] * sx, v[1]] for k, v in bolum.get("baslangic", {}).items()}
    for c in cekimler:
        for e in sorted(c.get("eylemler", []), key=lambda e: e["bas"]):
            if e["eylem"] in ("yuru", "kos", "atla") and "nereye" in e and e["kim"] in konum:
                hedef = [e["nereye"][0] * sx, e["nereye"][1]]
                p0 = konum[e["kim"]]
                if ((hedef[0] - p0[0]) ** 2 + (hedef[1] - p0[1]) ** 2) ** 0.5 < esik:
                    e["_kisa"] = True
                konum[e["kim"]] = hedef


def alt_cekimler(c, satirlar_c, fps, kesme=True):
    """Uzun çekimi konuşana yakın plan ve ara açılarla alt çekimlere böler (izlenme süresi: tek açı 4 sn'yi geçmez).
    Dokunulmaz: ışığı değişen, zaten yakın ya da kısa çekimler. Kesme hiçbir hareketin (yürüme, zıplama, el sallama...)
    ortasına düşmez; her alt çekim kalite denetiminde ayrı çekim olarak ölçülür. Döner: [alt çekim sözlüğü]."""
    bas, sure, n = c["bas"], c["sure"], c["kare_say"]
    eyl = [(bas + e["bas"] * sure, bas + e.get("son", e["bas"] + 0.01) * sure, e) for e in c.get("eylemler", [])]
    sade = (not kesme or c["id"] == "giris" or c.get("tip") == "yakin" or sure < 2 * KESME_EN_KISA + 0.5
            or c.get("isik_son", c.get("isik")) != c.get("isik"))
    if sade:
        return [dict(c)]

    def serbest(t):
        """Kesme t anına düşebilir mi: kısa hareketin ortası olmaz; uzun hareket (≥3.5 sn) en az 1.6 sn
        göründükten sonra kesilebilir (kalite ölçümü hareketi başladığı alt çekimde yine görür)."""
        for a, b, e in eyl:
            if e["eylem"] in KESILEBILIR or not (a - 0.1 < t < b + 0.1):
                continue
            if e["eylem"] in HAREKET and not e.get("_kisa"):  # yer değiştirme, hareketin tamamı tek alt çekimde ölçülür
                return False
            if not (b - a >= 3.5 and t - a >= KESME_EN_KISA and b - t >= 0.5):
                return False
        return True

    def hareketli(t):
        return any(a <= t <= b for a, b, e in eyl if e["eylem"] in HAREKET and not e.get("_kisa"))

    # aday kesmeler: hedefteki bir karakterin satır başı (biraz önce: kesme konuşmadan hemen önce gelsin)
    aday = [(s["bas"] - 0.12, s["kim"]) for s in satirlar_c if s["kim"] in c["hedef"]]
    sinirlar, son = [(bas, None)], bas
    for t, kim in aday:
        if t - son >= KESME_EN_KISA and bas + sure - t >= KESME_EN_KISA and serbest(t):
            sinirlar.append((t, kim))
            son = t
    # hâlâ uzun kalan parçaları ortadan böl (ara açı)
    tam, i = [], 0
    noktalar = sinirlar + [(bas + sure, None)]
    for (a, kim), (b, _) in zip(noktalar, noktalar[1:]):
        tam.append((a, kim))
        t = a
        while b - t > KESME_EN_UZUN:
            ideal = t + min(KESME_EN_UZUN, (b - t) / 2)
            # ideal an bir hareketin içindeyse en yakın uygun ana kay (her iki yanda en az KESME_EN_KISA kalsın)
            adaylar = [t + KESME_EN_KISA + 0.1 * q for q in range(int((b - t - 2 * KESME_EN_KISA) / 0.1) + 1)]
            uygun = [x for x in adaylar if serbest(x)]
            if not uygun:
                break
            orta = min(uygun, key=lambda x: abs(x - ideal))
            tam.append((orta, "ara"))
            t = orta
    out = []
    kareler = [int(round((t - bas) * fps)) for t, _ in tam] + [n]
    for j, (t, kim) in enumerate(tam):
        k0, k1 = kareler[j], kareler[j + 1]
        if k1 - k0 <= 0:
            continue
        a2 = dict(c, id=f"{c['id']}" if j == 0 else f"{c['id']}_{j}", bas_kare=c["bas_kare"] + k0, kare_say=k1 - k0)
        a2["bas"], a2["sure"] = a2["bas_kare"] / fps, a2["kare_say"] / fps
        if j and kim not in (None, "ara") and not hareketli(t + 0.2):  # konuşana yakın plan
            a2.update(tip="yakin", hedef=[kim], hareket="yaklas" if j % 2 else "sabit", taraf=-1 if j % 2 else 1)
        elif j:  # ara açı: bir önceki alt çekimden farklı tip ve öbür taraftan (kesmede açı gerçekten değişsin)
            onceki = out[-1]["tip"] if out else c.get("tip", "orta")
            # geniş açı ara açı olmaz: dikey kadrajda ekranı zeminle doldurur (b052: kontrast denetiminden kaldı)
            secenek = [x for x in (("orta", "iki_kisi") if len(c["hedef"]) == 2 else ("orta",)) if x != onceki] or ["orta"]
            a2.update(tip=secenek[j % len(secenek)], hareket=("kaydir", "donus")[j % 2],
                      taraf=-(out[-1].get("taraf", 1) if out else c.get("taraf", 1)))
        # eylemler, zamanı bu parçaya düşen alt çekimde kalır (kalite ölçümü doğru pencerede)
        a2["eylemler"] = [{**e, "bas": (ea - a2["bas"]) / a2["sure"], "son": (eb - a2["bas"]) / a2["sure"]}
                          for ea, eb, e in eyl if a2["bas"] - 1e-6 <= ea < a2["bas"] + a2["sure"]]
        out.append(a2)
    if out and out[0].get("hareket", "sabit") == "sabit" and len(out) > 1:
        out[0]["hareket"] = "yaklas"
    return out


def planla(seri_dizini, bolum_yolu, profil_adi, is_dizini, prototip=False):
    seri, bolum = yukle(seri_dizini, bolum_yolu)
    prof = profil_al(profil_adi, prototip)
    fps, en, boy = prof["fps"], prof["en"], prof["boy"]
    sx = prof["x_sikistir"]
    is_dizini = Path(is_dizini)
    (is_dizini / "ses").mkdir(parents=True, exist_ok=True)

    kar_tanim = {k: v for k, v in seri["karakterler"].items() if v["tur"] != "ses"}
    cekimler = cekim_listesi(seri, bolum, profil_adi, prototip)
    bolum = dict(bolum, baslangic=karakterleri_ayir(bolum, cekimler, sx))
    # Doğal ses: bölümün TÜM Türkçe satırları Gemini ses kütüphanesindeyse onlar, değilse bölümün tamamı edge-tts
    gayar = gemini_ses.sesler(seri)
    dogal = None if os.environ.get("GEMINI_SES") == "kapali" else gemini_ses.bolum_sesleri(turkce_satirlar(cekimler), gayar)
    print("ses:", "Gemini (kütüphane)" if dogal else "edge-tts", flush=True)
    (is_dizini / "ses_kaynagi.txt").write_text("gemini" if dogal else "edge")

    # 1) seslendirme ve çekim süreleri
    zaman = 0.0
    satirlar, kelimeler = [], []
    for c in cekimler:
        t = BASLANGIC_PAY
        for i, s in enumerate(c.get("satirlar", [])):
            # İngilizce ders satırı (dil: en) yerli İngilizce sesle okunur; Türkçe ses İngilizceyi bozar
            kar = seri["karakterler"][s["kim"]]
            prof_ses = kar.get("ses_en", kar["ses"]) if s.get("dil") == "en" else kar["ses"]
            anahtar = hashlib.md5((s["metin"] + json.dumps(prof_ses, sort_keys=True)).encode()).hexdigest()[:12]
            npy = is_dizini / "ses" / f"{anahtar}.npy"
            kj = is_dizini / "ses" / f"{anahtar}.json"
            if dogal and s.get("dil", "tr") != "en":
                sinyal, kel = dogal[(s["kim"], s["metin"])]
            elif npy.exists() and kj.exists():
                sinyal, kel = np.load(npy), [tuple(x) for x in json.loads(kj.read_text())]
            else:
                sinyal, kel = ses3d.satir_seslendir(s["metin"], prof_ses, is_dizini / "ses", anahtar)
                np.save(npy, sinyal)
                kj.write_text(json.dumps(kel, ensure_ascii=False))
            if bolum.get("tur") == "ingilizce":
                # TTS her satırın sonuna ~1 sn sessizlik koyar; derste tekrar payı "bekle" ile ayrıca verilir,
                # bu yüzden kırpılır (ders 56 sn -> ~44 sn). Masal bölümlerinin ritmi değişmesin diye yalnız derste.
                sinyal = _sessizlik_kirp(sinyal, kel)
            bas = zaman + t
            satirlar.append({"kim": s["kim"], "bas": bas, "sinyal": sinyal, "metin": s["metin"], "cekim": c["id"],
                             "dil": s.get("dil", "tr"), "anlam": s.get("anlam")})
            kelimeler += [{"bas": bas + a, "son": bas + b, "metin": m, "kim": s["kim"], "dil": s.get("dil", "tr")}
                          for a, b, m in kel]
            # "bekle": çocuğun tekrar etmesi için satırdan sonra sessiz pay (sn, en çok 2.5)
            t += len(sinyal) / SR + SATIR_ARASI + min(2.5, max(0.0, float(s.get("bekle", 0))))
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
    _kisa_yuruyusleri_isaretle(cekimler, bolum, sx)
    kam, isik = [], []
    alt = []
    for c in cekimler:
        c["hedef"] = [h for h in c.get("hedef", list(karakterler)) if h in karakterler] or list(karakterler)
        alt += alt_cekimler(c, [s for s in satirlar if s["cekim"] == c["id"]], fps,
                            kesme=os.environ.get("KESME") != "kapali")
    if prof.get("giris_cekimi") is False and alt and alt[0].get("hareket", "sabit") == "sabit":
        alt[0]["hareket"] = "hizli_yaklas"  # Shorts: ilk 2 saniyede hareket (kaydırmayı durdursun)
    for c in alt:  # koşu/yürüyüş olan geniş çekimde kamera yolu sığdırmak için uzaklaşmasın, takip etsin
        if c.get("tip") == "genis" and c.get("hareket") != "takip" and c["id"] != "giris" and any(
                e["eylem"] in HAREKET and not e.get("_kisa") and e["kim"] in c["hedef"] for e in c.get("eylemler", [])):
            c["hareket"] = "takip"
            if en < boy:  # dikey: koşanları büyük göster (geniş takipte de zemin baskın kalıyordu)
                c["tip"] = "orta"
    cekimler = alt
    for c in cekimler:
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
            if e["eylem"] == "kos":
                ekle("vin", e["bas"])
            aralik = 0.2 if e["eylem"] == "kos" else 0.3
            t = e["bas"] + 0.1
            while t < e["son"] - 0.05:
                ekle("adim", t)
                t += aralik
        elif e["eylem"] == "atla":
            ekle("vin", e["bas"] + 0.15 * (e["son"] - e["bas"]))
            ekle("adim", e["son"] - 0.03)
        elif e["eylem"] == "ac":
            ekle("hazine", e["bas"] + 0.5 * (e["son"] - e["bas"]))
        elif e["eylem"] == "tut":
            ekle("pop", e["bas"] + 0.45 * (e["son"] - e["bas"]))
        elif e["eylem"] == "ver":
            ekle("pop", e["bas"] + 0.5 * (e["son"] - e["bas"]))
            ekle("parilti", e["bas"] + 0.55 * (e["son"] - e["bas"]))

    tohum = int(hashlib.md5(bolum["baslik"].encode()).hexdigest()[:8], 16)
    muzik = ses3d.muzik(n, tohum, macera=bolum.get("muzik") == "macera")
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
                        "eylemler": [e["eylem"] for e in c.get("eylemler", []) if not e.get("_kisa")]}
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
        # İngilizce kelime kartı: "anlam"ı olan İngilizce satır boyunca (+ tekrar payı) ekranın üstünde
        "kartlar": [{"bas": round(s["bas"], 3), "son": round(s["bas"] + len(s["sinyal"]) / SR + KART_TUT, 3),
                     "en": s["metin"].strip(" .!?"), "tr": s["anlam"]} for s in satirlar if s.get("anlam")],
        "efektler": efektler,
        "ses": {"ornek": n, "konusma_muzik_db": ses3d.konusma_muzik_farki_db(konusma, muzik_son, maske),
                "konusma_ornek": int(maske.sum())},
        "zarflar": _yuvarla(zarflar),
        "karakter_adlari": {k: v["ad"] for k, v in seri["karakterler"].items()},
    }
    (is_dizini / "kurgu.json").write_text(json.dumps(kurgu, ensure_ascii=False))
    return plan, kurgu
