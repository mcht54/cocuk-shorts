"""Bölüm dosyası denetimi (render'dan önce, ağsız): yapı, eylem kuralları, sahnedeki tutarlılık,
tahmini süre ve içerik filtresi. Render saatlerce sürdüğü için hatalı senaryo burada durdurulur.

Kullanım: python -m cocuk3d.bolum_denetle seri/findik-ile-pamuk   -> hatalar; çıkış 1 = hata var
"""
import json
import math
import sys
from pathlib import Path

from cocuk.senaryo import YASAK
from cocuk3d.animasyon import IFADELER
from cocuk3d.kamera import ISIK, TIPLER

EYLEMLER = {"yuru", "kos", "zipla", "el_salla", "tut", "ver", "ifade", "bak", "otur", "kalk"}
HAREKETLER = {"sabit", "yaklas", "uzaklas", "donus", "kaydir", "takip"}
SAHNE_X, SAHNE_Y = (-1.8, 1.8), (-0.3, 0.6)
UZANMA = 0.45        # tut: karakter nesneye bu kadar yakın olmalı (yoksa nesne ele ışınlanır)
VERME = 1.2          # ver: iki karakter arası en çok
KELIME_SN = 0.67     # ölçüm (b001 Shorts): 46 kelime 30.8 sn konuşma
SATIR_ARASI, CEKIM_SONU = 0.3, 0.45
SHORTS_EN_COK = 55.0  # profil sınırı 59; seslendirme sapmasına pay


def tahmini_sure(bolum):
    toplam = 0.0
    for c in bolum["cekimler"]:
        t = sum(len(s["metin"].split()) * KELIME_SN + SATIR_ARASI for s in c["satirlar"])
        toplam += max(2.0, t + CEKIM_SONU)
    return toplam


def denetle(bolum, seri):
    h = []
    karakterler = {k for k, v in seri["karakterler"].items() if v.get("tur") != "ses"}
    konusanlar = set(seri["karakterler"])
    if bolum.get("mekan") not in seri["mekanlar"]:
        h.append(f"bilinmeyen mekan: {bolum.get('mekan')}")
    konum = {k: list(p) for k, p in bolum["baslangic"].items()}
    for k in konum:
        if k not in karakterler:
            h.append(f"başlangıçta bilinmeyen karakter: {k}")
    nesne = {n: list(p[:2]) for n, p in bolum.get("nesne_yerlesim", {}).items()}
    for n in nesne:
        if n not in seri["nesneler"]:
            h.append(f"bilinmeyen nesne: {n}")
    tutan = {n: None for n in nesne}
    oturuyor = {k: False for k in konum}

    for c in bolum["cekimler"]:
        ad = c["id"]
        if c["tip"] not in TIPLER:
            h.append(f"{ad}: bilinmeyen çekim tipi {c['tip']}")
        if c["hareket"] not in HAREKETLER:
            h.append(f"{ad}: bilinmeyen kamera hareketi {c['hareket']}")
        if c["isik"] not in ISIK:
            h.append(f"{ad}: bilinmeyen ışık {c['isik']}")
        if not c["hedef"] or any(x not in konum for x in c["hedef"]):
            h.append(f"{ad}: hedef sahnede değil: {c['hedef']}")
        if not c["satirlar"]:
            h.append(f"{ad}: satır yok")
        for s in c["satirlar"]:
            if s["kim"] not in konusanlar:
                h.append(f"{ad}: bilinmeyen konuşan {s['kim']}")
            if s["kim"] in karakterler and s["kim"] not in konum:
                h.append(f"{ad}: {s['kim']} sahnede değil ama konuşuyor")
            if YASAK.search(s["metin"]):
                h.append(f"{ad}: yasaklı kelime: {s['metin']}")
            if len(s["metin"].split()) > 14:
                h.append(f"{ad}: satır çok uzun ({len(s['metin'].split())} kelime)")
        for e in sorted(c["eylemler"], key=lambda e: e["bas"]):
            k, ey = e["kim"], e["eylem"]
            yer = f"{ad}/{k}/{ey}@{e['bas']}"
            if ey not in EYLEMLER:
                h.append(f"{yer}: bilinmeyen eylem")
                continue
            if k not in konum:
                h.append(f"{yer}: karakter sahnede değil")
                continue
            if not 0 <= e["bas"] <= 1 or ("son" in e and not e["bas"] < e["son"] <= 1):
                h.append(f"{yer}: zaman 0-1 aralığında değil")
            if ey in ("yuru", "kos"):
                x, y = e["nereye"]
                if not (SAHNE_X[0] <= x <= SAHNE_X[1] and SAHNE_Y[0] <= y <= SAHNE_Y[1]):
                    h.append(f"{yer}: hedef sahne dışında {e['nereye']}")
                if oturuyor[k]:
                    h.append(f"{yer}: otururken yürüyor (önce kalk)")
                konum[k] = [x, y]
            elif ey == "zipla" and oturuyor[k]:
                h.append(f"{yer}: otururken zıplıyor (önce kalk)")
            elif ey == "ifade" and e.get("tur") not in IFADELER:
                h.append(f"{yer}: bilinmeyen ifade {e.get('tur')}")
            elif ey == "bak":
                if "kime" in e and e["kime"] not in konum:
                    h.append(f"{yer}: bakılan karakter sahnede değil")
                if "kime" not in e and "yon" not in e:
                    h.append(f"{yer}: bak için kime ya da yon gerekli")
            elif ey == "otur":
                if oturuyor[k]:
                    h.append(f"{yer}: zaten oturuyor")
                oturuyor[k] = True
            elif ey == "kalk":
                if not oturuyor[k]:
                    h.append(f"{yer}: oturmuyor ama kalkıyor")
                oturuyor[k] = False
            elif ey == "tut":
                n = e.get("nesne")
                if n not in nesne:
                    h.append(f"{yer}: nesne yok: {n}")
                    continue
                if tutan[n] not in (None, k):
                    h.append(f"{yer}: {n} şu an {tutan[n]} elinde")
                elif tutan[n] is None and math.dist(konum[k], nesne[n]) > UZANMA:
                    h.append(f"{yer}: {n} çok uzakta ({math.dist(konum[k], nesne[n]):.2f} m > {UZANMA})")
                tutan[n] = k
            elif ey == "ver":
                n, alan = e.get("nesne"), e.get("kime")
                if tutan.get(n) != k:
                    h.append(f"{yer}: elinde {n} yok")
                if alan not in konum:
                    h.append(f"{yer}: alan karakter sahnede değil")
                elif math.dist(konum[k], konum[alan]) > VERME:
                    h.append(f"{yer}: alan çok uzakta ({math.dist(konum[k], konum[alan]):.2f} m)")
                tutan[n] = alan
            for n, t_ in tutan.items():
                if t_:
                    nesne[n] = konum[t_]
    sure = tahmini_sure(bolum)
    if sure > SHORTS_EN_COK:
        h.append(f"tahmini süre {sure:.0f} sn > {SHORTS_EN_COK:.0f} sn (Shorts)")
    if sure < 20:
        h.append(f"tahmini süre {sure:.0f} sn çok kısa")
    yt = bolum["youtube"]
    if len(yt["baslik"]) > 90:
        h.append(f"YouTube başlığı {len(yt['baslik'])} karakter (#shorts için en çok 90)")
    return h


def seriyi_denetle(seri_dizini):
    seri_dizini = Path(seri_dizini)
    seri = json.loads((seri_dizini / "seri.json").read_text())
    sonuc, basliklar = {}, {}
    for yol in sorted(seri_dizini.glob("bolumler/b*.json")):
        b = json.loads(yol.read_text())
        h = denetle(b, seri)
        if b["baslik"] in basliklar:
            h.append(f"başlık {basliklar[b['baslik']]} ile aynı")
        basliklar[b["baslik"]] = yol.name
        if h:
            sonuc[yol.name] = h
    return sonuc


if __name__ == "__main__":
    hatalar = seriyi_denetle(sys.argv[1] if len(sys.argv) > 1 else "seri/findik-ile-pamuk")
    for dosya, h in hatalar.items():
        print(dosya)
        for x in h:
            print("  -", x)
    print("hata yok" if not hatalar else f"{len(hatalar)} bölümde hata")
    sys.exit(1 if hatalar else 0)
