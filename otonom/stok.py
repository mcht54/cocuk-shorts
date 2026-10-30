"""Gece stok doldurma (stok.yml): iki kanalın yayınlanmayı bekleyen içeriği hedefin altındaysa yenisini yazar.

Hedefler ~3 hafta: Gemini bir süre çalışmasa da yayın durmaz. Bir çalıştırma en çok MASAL_TUR bölüm ve
MERAK_TUR konu yazar (ücretsiz katmanın günlük sınırına takılmamak için); açık her gün kapanır.
Kullanım: python -m otonom.stok [--kanal masal|merak|hepsi]   Çıkış 1 = beklenmeyen kod hatası (düşük stok sağlık denetiminde raporlanır).
"""
import argparse
import json
import os
import sys
from pathlib import Path

from ortak import gemini

DEPO = Path(__file__).resolve().parent.parent
SERI = DEPO / "seri" / "findik-ile-pamuk"
MASAL_HEDEF, MASAL_TUR = 21, 3
MERAK_UZUN_HEDEF, MERAK_KISA_HEDEF, MERAK_TUR = 6, 21, 2
KRITIK_GUN = 5


def ozet(metin):
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")
    print(metin, flush=True)


def masal_stogu():
    kayit = json.loads((DEPO / "yayin_kaydi.json").read_text()) if (DEPO / "yayin_kaydi.json").exists() else []
    yapilan = {k["bolum"] for k in kayit if k.get("profil") == "shorts" and k.get("durum") == "yuklendi"}
    kalan = {}
    for k in kayit:
        if k.get("profil") == "shorts" and k.get("durum") == "kalite_kaldi":
            kalan[k["bolum"]] = kalan.get(k["bolum"], 0) + 1
    return sum(1 for p in SERI.glob("bolumler/b*.json")
               if str(p.relative_to(DEPO)) not in yapilan and kalan.get(str(p.relative_to(DEPO)), 0) < 2)


HATALAR = []


def masal():
    from otonom import masal_yaz
    stok = masal_stogu()
    ozet(f"**Minik Masal Evi** bekleyen bölüm: {stok} (hedef {MASAL_HEDEF})")
    yazilan = 0
    for _ in range(min(MASAL_TUR, max(0, MASAL_HEDEF - stok))):
        no = max(int(p.stem[1:]) for p in SERI.glob("bolumler/b*.json")) + 1
        if masal_yaz.yaz_bir(no):
            yazilan += 1
    ozet(f"- yeni bölüm: {yazilan}")
    return stok + yazilan


def merak():
    from merak import konu, yaz, yayinla
    def say():
        return len(yayinla.sira("uzun")), len(yayinla.sira("shorts"))
    uzun, kisa = say()
    ozet(f"**Merak Arşivi** bekleyen uzun: {uzun} (hedef {MERAK_UZUN_HEDEF}), Shorts: {kisa} (hedef {MERAK_KISA_HEDEF})")
    for tur in range(MERAK_TUR):
        if uzun >= MERAK_UZUN_HEDEF and kisa >= MERAK_KISA_HEDEF:
            break
        # yarım kalmış konu (kaynak var, senaryo yok) önce tamamlanır
        yarim = [d.name for d in konu.KONULAR.glob("*") if (d / "kaynak.json").exists()
                 and not (d / "reddedildi").exists() and not (d / "uzun.json").exists()]
        kid = yarim[0] if yarim else konu.yeni_konu(tur)
        if not kid:
            ozet("- uygun konu bulunamadı (bu tur)")
            continue
        try:
            ok = yaz.yaz(kid)
        except gemini.GeminiYok:
            raise
        except Exception as e:  # kod hatası: konu bırakılır (her gün aynı yerde takılmasın), iş kırmızı biter
            (konu.KONULAR / kid / "reddedildi").write_text(f"beklenmeyen hata: {e!r}\n")
            HATALAR.append(f"merak {kid}: {e!r}")
            ok = False
        ozet(f"- {kid}: {'senaryolar yazıldı' if ok else 'senaryo denetimi geçemedi, konu bırakıldı'}")
        uzun, kisa = say()
    return uzun, kisa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kanal", default="hepsi", choices=["masal", "merak", "hepsi"])
    a = ap.parse_args()
    kritik = []
    for ad, is_ in (("masal", masal), ("merak", merak)):
        if a.kanal not in (ad, "hepsi"):
            continue
        try:
            sonuc = is_()
        except gemini.GeminiYok as e:
            ozet(f"- {ad}: Gemini kullanılamadı ({e}); stok yarın yeniden denenecek")
            sonuc = masal_stogu() if ad == "masal" else None
        if ad == "masal" and sonuc is not None and sonuc < KRITIK_GUN:
            kritik.append(f"Minik Masal Evi stoku {sonuc} bölüm")
        if ad == "merak" and isinstance(sonuc, tuple) and sonuc[1] < KRITIK_GUN:
            kritik.append(f"Merak Arşivi Shorts stoku {sonuc[1]}")
    for k in kritik:
        ozet(f"⚠️ KRİTİK: {k}")
    for h in HATALAR:
        ozet(f"❌ HATA: {h}")
    # düşük stok sağlık denetiminin işidir (tek e-posta); stok işi yalnız kod hatasında kırmızı biter
    return 1 if HATALAR else 0


if __name__ == "__main__":
    sys.exit(main())
