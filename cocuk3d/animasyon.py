"""Karakter animasyonunun kare kare hesaplanması (Blender'dan bağımsız, test edilebilir).

Her karakter için her karede bir poz üretilir:
  konum [x, y, z], yon (z ekseni etrafında, radyan; 0 = kameraya/–Y'ye bakar),
  kemik {ad: [rx, ry, rz]} (kemiğin yerel ekseninde), olcek {ad: [sx, sy, sz]}.
Blender betiği bu değerleri iskelete anahtar kare olarak yazar.

Eylemler (saniye cinsinden bölüm zaman çizelgesinde):
  yuru/kos {nereye:[x,y]}, zipla {kez}, otur, kalk, el_salla, tut {nesne},
  ver {nesne, kime}, bak {kime | yon}, ifade {tur: normal|mutlu|uzgun|saskin}
Konuşma ağız hareketi ses zarfından (0-1) gelir; göz kırpma ve nefes her zaman açıktır.
"""
import math
import random
import zlib

KEMIKLER = ["govde", "bas", "kol.L", "kol.R", "bacak.L", "bacak.R", "kuyruk",
            "kulak.L", "kulak.R", "kas.L", "kas.R"]
OLCEKLER = ["agiz", "goz.L", "goz.R", "govde"]


def _tohum(metin):
    """Süreçten bağımsız sabit tohum (Python hash() her çalıştırmada değişir)."""
    return zlib.crc32(metin.encode())


def _yumusak(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def _aci_farki(a, b):
    return (b - a + math.pi) % (2 * math.pi) - math.pi


def _yon_hesapla(dx, dy):
    """(dx, dy) yönünde yürürken yüz yönü. yon=0 iken karakter –Y'ye bakar."""
    return math.atan2(dx, -dy)


class Durum:
    """Bir karakterin bölüm boyunca süren durumu (konum, yön, oturuş, ifade, elindeki nesne)."""

    def __init__(self, konum, yon=0.0):
        self.konum = list(konum)
        self.yon = yon
        self.hedef_yon = yon
        self.oturuyor = 0.0
        self.ifade = "normal"
        self.ifade_gecis = 1.0
        self.onceki_ifade = "normal"


IFADELER = {
    #            kaş rx/rz (iç uç), kulak eğim, baş eğim, ağız genişlik, göz boyu, ağız açıklık
    "normal": {"kas": 0.0, "kulak": 0.0, "bas": 0.0, "agiz_x": 1.0, "goz": 1.0, "agiz_z": 1.0},
    "mutlu": {"kas": 0.08, "kulak": -0.1, "bas": -0.08, "agiz_x": 1.35, "goz": 1.0, "agiz_z": 1.3},
    "uzgun": {"kas": 0.45, "kulak": 0.75, "bas": 0.28, "agiz_x": 0.75, "goz": 0.85, "agiz_z": 0.8},
    "saskin": {"kas": 0.22, "kulak": -0.2, "bas": -0.05, "agiz_x": 0.9, "goz": 1.25, "agiz_z": 1.6},
    "kararli": {"kas": -0.2, "kulak": -0.25, "bas": 0.06, "agiz_x": 0.85, "goz": 0.92, "agiz_z": 0.8},
}


def _ifade_degeri(durum, anahtar):
    u = _yumusak(durum.ifade_gecis)
    a = IFADELER[durum.onceki_ifade][anahtar]
    b = IFADELER[durum.ifade][anahtar]
    return a + (b - a) * u


def kirpma_takvimi(sure, tohum):
    """Göz kırpma başlangıç zamanları (2.2-4.2 sn aralıkla, tekrarlanabilir)."""
    r = random.Random(tohum)
    t, liste = r.uniform(0.6, 2.0), []
    while t < sure:
        liste.append(t)
        t += r.uniform(2.2, 4.2)
    return liste


KIRPMA = [0.55, 0.15, 0.08, 0.35, 0.8]
AGIZ_EN_COK = 2.8  # ağız dikey ölçeği üst sınırı  # 5 kare boyunca göz yüksekliği


def hesapla(karakterler, eylemler, sure, fps, zarflar, nesneler):
    """
    karakterler: {id: {"konum": [x, y], "boy": float, "tur": str}}
    eylemler: [{"kim", "eylem", "bas", "son", ...}] (saniye)
    zarflar: {id: [0-1 değerleri, kare başına]} konuşma zarfı
    nesneler: {nesne_id: {"konum": [x, y, z]}}
    Dönüş: (pozlar {id: [poz kare 0..n-1]}, nesne_tutma {nesne: [ {kim: etki} kare başına ]})
    """
    n = int(round(sure * fps))
    durumlar = {k: Durum([v["konum"][0], v["konum"][1], 0.0], v.get("yon", 0.0))
                for k, v in karakterler.items()}
    kirpmalar = {k: kirpma_takvimi(sure, _tohum(k) % 10007) for k in karakterler}
    tutan = {nid: None for nid in nesneler}  # şu an nesneyi tutan karakter
    pozlar = {k: [] for k in karakterler}
    tutma = {nid: [] for nid in nesneler}
    acik = {nid: 0.0 for nid in nesneler}  # sandık kapağı açıklığı (0-1), "ac" eylemiyle
    eylemler = sorted(eylemler, key=lambda e: e["bas"])
    baslamis = set()
    yuru_bas = {}  # id(eylem) -> başlangıç konumu
    adim_faz = {k: 0.0 for k in karakterler}

    for f in range(n):
        t = f / fps
        aktif = {k: [] for k in karakterler}
        for i, e in enumerate(eylemler):
            if e["bas"] <= t < e["son"]:
                aktif[e["kim"]].append((i, e))
            if e["bas"] <= t and i not in baslamis:
                baslamis.add(i)
                d = durumlar[e["kim"]]
                if e["eylem"] in ("yuru", "kos", "atla"):
                    yuru_bas[i] = list(d.konum[:2])
                elif e["eylem"] == "ifade":
                    d.onceki_ifade, d.ifade, d.ifade_gecis = d.ifade, e["tur"], 0.0
                elif e["eylem"] == "bak":
                    if "kime" in e:
                        o = durumlar[e["kime"]].konum
                        d.hedef_yon = _yon_hesapla(o[0] - d.konum[0], o[1] - d.konum[1])
                    else:
                        d.hedef_yon = e.get("yon", 0.0)

        for k, kar in karakterler.items():
            d = durumlar[k]
            boy = kar.get("boy", 1.0)
            kem = {b: [0.0, 0.0, 0.0] for b in KEMIKLER}
            olc = {b: [1.0, 1.0, 1.0] for b in OLCEKLER}
            z = 0.0
            yuruyor = False

            for i, e in aktif[k]:
                u = (t - e["bas"]) / max(1e-6, e["son"] - e["bas"])
                ad = e["eylem"]
                if ad in ("yuru", "kos"):
                    yuruyor = True
                    p0, p1 = yuru_bas[i], e["nereye"]
                    s = _yumusak(u)
                    yeni = [p0[0] + (p1[0] - p0[0]) * s, p0[1] + (p1[1] - p0[1]) * s]
                    adim = math.dist(yeni, d.konum[:2])
                    d.konum[0], d.konum[1] = yeni
                    adim_boyu = (0.5 if ad == "kos" else 0.32) * boy
                    adim_faz[k] += adim / adim_boyu * math.pi
                    gen = 0.75 if ad == "kos" else 0.5
                    ph = adim_faz[k]
                    hiz_carpani = min(1.0, adim * fps / (0.4 * boy) + 0.15)
                    kem["bacak.L"][0] = gen * math.sin(ph) * hiz_carpani
                    kem["bacak.R"][0] = -gen * math.sin(ph) * hiz_carpani
                    kem["kol.L"][0] = -0.8 * gen * math.sin(ph) * hiz_carpani
                    kem["kol.R"][0] = 0.8 * gen * math.sin(ph) * hiz_carpani
                    z += (0.05 if ad == "kos" else 0.03) * boy * abs(math.sin(ph)) * hiz_carpani
                    kem["govde"][0] += (-0.18 if ad == "kos" else -0.06) * hiz_carpani
                    if math.dist(p0, p1) > 0.05:
                        d.hedef_yon = _yon_hesapla(p1[0] - p0[0], p1[1] - p0[1])
                    if u > 0.97 and not e.get("arkasi_donuk"):
                        d.hedef_yon = e.get("son_yon", 0.0)
                elif ad == "atla":  # bir noktadan ötekine uzun sıçrayış (dere taşları, engeller)
                    yuruyor = True
                    p0, p1 = yuru_bas[i], e["nereye"]
                    if u < 0.2:  # hazırlan: çömel, kollar geri
                        c_ = math.sin(u / 0.2 * math.pi / 2)
                        olc["govde"] = [1 + 0.1 * c_, 1 + 0.1 * c_, 1 - 0.16 * c_]
                        z -= 0.05 * boy * c_
                        kem["kol.L"][0] = kem["kol.R"][0] = 0.9 * c_
                    else:
                        v = (u - 0.2) / 0.8
                        s = _yumusak(v)
                        d.konum[0], d.konum[1] = p0[0] + (p1[0] - p0[0]) * s, p0[1] + (p1[1] - p0[1]) * s
                        z += 0.5 * boy * 4 * v * (1 - v)
                        olc["govde"] = [0.95, 0.95, 1.08]
                        kem["kol.L"][2] = -1.9 * math.sin(v * math.pi)
                        kem["kol.R"][2] = 1.9 * math.sin(v * math.pi)
                        kem["bacak.L"][0] = -0.6 * math.sin(v * math.pi)
                        kem["bacak.R"][0] = 0.5 * math.sin(v * math.pi)
                    if math.dist(p0, p1) > 0.05:
                        d.hedef_yon = _yon_hesapla(p1[0] - p0[0], p1[1] - p0[1])
                    if u > 0.97:
                        d.hedef_yon = e.get("son_yon", d.hedef_yon)
                elif ad == "ac":  # sandık aç: iki kol öne, kapak kalkar
                    uzan = math.sin(min(1.0, u / 0.4) * math.pi / 2)
                    kem["kol.L"][0] = kem["kol.R"][0] = -1.2 * uzan
                    acik[e["nesne"]] = max(acik[e["nesne"]], _yumusak(min(1.0, max(0.0, (u - 0.3) / 0.5))))
                elif ad == "zipla":
                    kez = e.get("kez", 1)
                    uu = (u * kez) % 1.0
                    if uu < 0.18:  # çömel
                        c = math.sin(uu / 0.18 * math.pi)
                        olc["govde"] = [1 + 0.12 * c, 1 + 0.12 * c, 1 - 0.18 * c]
                        z -= 0.04 * boy * c
                    else:
                        v = (uu - 0.18) / 0.82
                        z += 0.38 * boy * 4 * v * (1 - v)
                        olc["govde"] = [0.94, 0.94, 1.1]
                        # kalibrasyon (önden render): kol.R +rz ve kol.L –rz kolu yana-yukarı kaldırır
                        kem["kol.L"][2] = -2.2 * math.sin(v * math.pi)
                        kem["kol.R"][2] = 2.2 * math.sin(v * math.pi)
                        kem["bacak.L"][0] = kem["bacak.R"][0] = -0.35 * math.sin(v * math.pi)
                elif ad == "el_salla":
                    kalk = _yumusak(min(1.0, u * 5)) * _yumusak(min(1.0, (1 - u) * 5))
                    kem["kol.R"][2] = (2.5 + 0.35 * math.sin(t * 2 * math.pi * 2.5)) * kalk
                elif ad == "tut":
                    uzan = math.sin(min(1.0, u / 0.6) * math.pi / 2)
                    kem["kol.R"][0] = -1.3 * uzan
                    kem["govde"][0] += 0.25 * math.sin(min(1.0, u / 0.6) * math.pi)
                    if u > 0.45:
                        tutan[e["nesne"]] = k
                elif ad == "ver":
                    uzan = math.sin(min(1.0, u / 0.5) * math.pi / 2) * _yumusak((1 - u) * 4)
                    kem["kol.R"][0] = -1.5 * uzan
                    if u > 0.5:
                        tutan[e["nesne"]] = e["kime"]

            # durumsal: oturma, yön dönüşü, ifade geçişi
            oturma_hedef = d.oturuyor
            for _, e in aktif[k]:
                if e["eylem"] == "otur":
                    oturma_hedef = _yumusak((t - e["bas"]) / 0.5)
                elif e["eylem"] == "kalk":
                    oturma_hedef = 1 - _yumusak((t - e["bas"]) / 0.5)
            d.oturuyor = oturma_hedef
            d.yon += _aci_farki(d.yon, d.hedef_yon) * min(1.0, 9.0 / fps)
            d.ifade_gecis = min(1.0, d.ifade_gecis + 2.5 / fps)

            if d.oturuyor > 0:
                z -= 0.17 * boy * d.oturuyor
                kem["bacak.L"][0] += -1.35 * d.oturuyor
                kem["bacak.R"][0] += -1.35 * d.oturuyor

            # elinde nesne varsa kol öne
            if any(v == k for v in tutan.values()) and not any(e["eylem"] in ("ver", "tut", "zipla")
                                                                for _, e in aktif[k]):
                kem["kol.R"][0] = min(kem["kol.R"][0], -0.9) if not yuruyor else -0.9

            # her zaman: nefes, baş salınımı, kuyruk
            nefes = math.sin(t * 2 * math.pi * 0.35 + _tohum(k) % 7)
            olc["govde"][2] *= 1 + 0.018 * nefes
            kem["bas"][1] += 0.05 * math.sin(t * 2 * math.pi * 0.23 + _tohum(k) % 5)
            # beklerken de canlı dursun: kollar ve gövde hafifçe salınır (ölçüm 2026-10-30:
            # yalnız nefesle duran orta çekimler 1.2 sn "donuk" kaldı, uzuv sapması 0.007 m)
            if not yuruyor:
                faz = _tohum(k) % 11
                kem["kol.L"][2] += 0.10 * math.sin(t * 2 * math.pi * 0.5 + faz)
                kem["kol.R"][2] -= 0.10 * math.sin(t * 2 * math.pi * 0.5 + faz + 1.3)
                kem["kol.L"][0] += 0.06 * math.sin(t * 2 * math.pi * 0.37 + faz)
                kem["kol.R"][0] += 0.06 * math.sin(t * 2 * math.pi * 0.41 + faz + 0.7)
                kem["bas"][2] += 0.06 * math.sin(t * 2 * math.pi * 0.17 + faz)
            kem["kuyruk"][0] = 0.15 * math.sin(t * 2 * math.pi * (1.4 if yuruyor else 0.6))
            kem["kuyruk"][2] = 0.12 * math.sin(t * 2 * math.pi * 0.9)

            # ifade
            kas = _ifade_degeri(d, "kas")
            kem["kas.L"][1] = -kas  # kalibrasyon: +değer iç ucu indirir (kızgın görünüm)
            kem["kas.R"][1] = kas
            kem["kulak.L"][0] += _ifade_degeri(d, "kulak")
            kem["kulak.R"][0] += _ifade_degeri(d, "kulak")
            kem["kulak.L"][1] -= 0.25 * _ifade_degeri(d, "kulak")
            kem["kulak.R"][1] += 0.25 * _ifade_degeri(d, "kulak")
            kem["bas"][0] += _ifade_degeri(d, "bas")
            goz = _ifade_degeri(d, "goz")

            # konuşma: ağız + hafif baş hareketi
            zarf = zarflar.get(k, [])
            e_ = zarf[f] if f < len(zarf) else 0.0
            # üst sınır: ifade × konuşma çarpımı ağzı "sarkan dil" gibi uzatıyordu (5.7×)
            olc["agiz"] = [_ifade_degeri(d, "agiz_x") * (1 - 0.15 * e_), 1.0,
                           min(AGIZ_EN_COK, _ifade_degeri(d, "agiz_z") * (1 + 2.6 * e_))]
            kem["bas"][0] += -0.06 * e_

            # göz kırpma
            g = goz
            for kb in kirpmalar[k]:
                j = int(round((t - kb) * fps))
                if 0 <= j < len(KIRPMA):
                    g = goz * KIRPMA[j]
            olc["goz.L"] = [goz, 1.0, g]
            olc["goz.R"] = [goz, 1.0, g]

            pozlar[k].append({"konum": [d.konum[0], d.konum[1], z], "yon": d.yon,
                              "kemik": kem, "olcek": olc})

        for nid in nesneler:
            durum_ = {tutan[nid]: 1.0} if tutan[nid] else {}
            if acik[nid]:
                durum_["_ac"] = round(acik[nid], 4)
            tutma[nid].append(durum_)

    return pozlar, tutma


def son_konumlar(pozlar):
    return {k: p[-1]["konum"][:2] for k, p in pozlar.items() if p}
