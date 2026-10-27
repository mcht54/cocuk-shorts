"""Çekim türüne ve kadraja (9:16 / 16:9) göre kamera yolu ve ışık ön ayarları.

Kamera, hedef karakterleri kadraja sığdıracak uzaklığı görüş açısından hesaplar;
böylece dikey Shorts'ta da yatay bölümde de karakterler kadraj içinde kalır.
"""
import math

SENSOR = 36.0  # mm; Blender sensor_fit=AUTO -> uzun kenara uygulanır

TIPLER = {
    #          lens, yükseklik, bakış yüksekliği, yatay açı, pay çarpanı, odak (baş/gövde)
    "genis": {"lens": 30, "yuk": 1.9, "bakis": 0.55, "aci": 0.18, "pay": 1.9},
    "orta": {"lens": 40, "yuk": 1.05, "bakis": 0.6, "aci": 0.22, "pay": 1.25},
    "yakin": {"lens": 55, "yuk": 0.85, "bakis": 0.78, "aci": 0.15, "pay": 1.0},
    "iki_kisi": {"lens": 38, "yuk": 1.15, "bakis": 0.6, "aci": 0.0, "pay": 1.05},
}


def gorus_acilari(lens, en, boy):
    """(yatay, dikey) görüş açısı, radyan."""
    uzun = 2 * math.atan(SENSOR / 2 / lens)
    kisa = 2 * math.atan(SENSOR / 2 * min(en, boy) / max(en, boy) / lens)
    return (uzun, kisa) if en >= boy else (kisa, uzun)


def cerceve_uzakligi(tip, hedef_genislik, hedef_yukseklik, en, boy):
    t = TIPLER[tip]
    yatay, dikey = gorus_acilari(t["lens"], en, boy)
    yg = hedef_genislik * t["pay"] / 2
    yy = hedef_yukseklik * t["pay"] / 2
    return max(yg / math.tan(yatay / 2), yy / math.tan(dikey / 2))


def kamera_yolu(cekim, pozlar, boylar, bas_kare, kare_say, en, boy):
    """Çekimin her karesi için {"konum", "hedef", "lens"} üretir."""
    tip = cekim.get("tip", "orta")
    t = TIPLER[tip]
    hedefler = cekim.get("hedef") or list(pozlar)
    hareket = cekim.get("hareket", "sabit")
    yol = []
    yumusak_merkez = None
    for j in range(kare_say):
        f = bas_kare + j
        u = j / max(1, kare_say - 1)
        xs = [pozlar[h][f]["konum"][0] for h in hedefler]
        ys = [pozlar[h][f]["konum"][1] for h in hedefler]
        boy_en = max(boylar[h] for h in hedefler)
        if hareket == "takip" or yumusak_merkez is None:
            merkez = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]
            if yumusak_merkez is None:
                yumusak_merkez = merkez
            else:  # yumuşak takip
                yumusak_merkez = [a + (b - a) * 0.12 for a, b in zip(yumusak_merkez, merkez)]
        if j == 0:
            # kadraj çekimin tamamını kapsasın: yürüyen karakter kadrajdan çıkmasın
            tum_x = [pozlar[h][bas_kare + q]["konum"][0] for h in hedefler for q in range(kare_say)]
            tum_y = [pozlar[h][bas_kare + q]["konum"][1] for h in hedefler for q in range(kare_say)]
            if hareket != "takip":
                yumusak_merkez = [(min(tum_x) + max(tum_x)) / 2, (min(tum_y) + max(tum_y)) / 2]
                xs = tum_x
            genislik = (max(xs) - min(xs)) + 0.7 * boy_en
            yukseklik = (0.8 if tip == "yakin" else 1.25) * boy_en  # yakın: baş + omuz (0.55 yatayda başı kesiyordu)
            d0 = cerceve_uzakligi(tip, genislik, yukseklik, en, boy)
        d, aci = d0, t["aci"] * cekim.get("taraf", 1)
        if len(hedefler) == 1 and tip in ("yakin", "orta"):
            # tek karakter: kamerayı yüzünün önüne al (dönüş bitmiş bir kareden yön oku)
            fy = min(bas_kare + kare_say - 1, bas_kare + 12)
            yon = pozlar[hedefler[0]][fy]["yon"]
            aci += max(-1.1, min(1.1, (yon + math.pi) % (2 * math.pi) - math.pi))
        if hareket == "yaklas":
            d = d0 * (1.18 - 0.28 * u)
        elif hareket == "uzaklas":
            d = d0 * (0.92 + 0.3 * u)
        elif hareket == "donus":
            aci += -0.35 + 0.7 * u
        elif hareket == "kaydir":
            aci += -0.2 + 0.4 * u
        mx, my = yumusak_merkez
        bakis_z = t["bakis"] * boy_en
        yol.append({
            "konum": [mx + d * math.sin(aci), my - d * math.cos(aci), t["yuk"] * boy_en + 0.04 * d],
            "hedef": [mx, my, bakis_z],
            "lens": t["lens"],
        })
    return yol


ISIK = {
    "sabah": {"gunes": 3.2, "renk": [1.0, 0.92, 0.80], "egim": 52, "yon": 35,
              "gok": [0.55, 0.74, 1.0], "gok_guc": 0.9},
    "ogle": {"gunes": 4.2, "renk": [1.0, 0.98, 0.95], "egim": 30, "yon": 15,
             "gok": [0.62, 0.80, 1.0], "gok_guc": 1.0},
    "aksam": {"gunes": 2.6, "renk": [1.0, 0.60, 0.36], "egim": 74, "yon": -55,
              "gok": [0.95, 0.62, 0.55], "gok_guc": 0.7},
    "gece": {"gunes": 0.5, "renk": [0.55, 0.65, 1.0], "egim": 60, "yon": 20,
             "gok": [0.10, 0.12, 0.30], "gok_guc": 0.35},
    "ic_mekan": {"gunes": 1.6, "renk": [1.0, 0.88, 0.72], "egim": 45, "yon": 60,
                 "gok": [0.95, 0.85, 0.75], "gok_guc": 0.8},
}


def isik_yolu(cekim, kare_say):
    a = ISIK[cekim.get("isik", "sabah")]
    b = ISIK[cekim.get("isik_son", cekim.get("isik", "sabah"))]
    yol = []
    for j in range(kare_say):
        u = j / max(1, kare_say - 1)
        yol.append({k: ([x + (y - x) * u for x, y in zip(a[k], b[k])] if isinstance(a[k], list)
                        else a[k] + (b[k] - a[k]) * u) for k in a})
    return yol
