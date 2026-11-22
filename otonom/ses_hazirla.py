"""Gece ses hazırlığı: sıradaki bölümlerin Türkçe satırlarını Gemini ile seslendirip ses_kutuphane/ altına yazar.

Yalnız TR 22:00–10:30 arasında çalışır (Dijital Çırak'ın aynı ücretsiz ses kotasını gündüz kullanması için) ve bir
çalışmada en çok BUTCE istek yapar. Kota/bütçe biterse sessizce durur; kalan bölümler sonraki gece hazırlanır.
Render hiçbir zaman bunu beklemez: kütüphanede olmayan bölüm edge-tts sesiyle çizilir.
Kullanım: python -m otonom.ses_hazirla [--adet 2] [--butce 5] [--bolum seri/.../b052.json] [--zorla]
"""
import argparse
import json
import os
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import bulut3d  # noqa: E402
from cocuk3d import gemini_ses, planla  # noqa: E402

SERI = KOK / "seri" / "findik-ile-pamuk"


def bolum_satirlari(seri, bolum):
    """Shorts satırları + uzun derlemenin giriş satırı (uzunda atılan "Yarın devam!" kütüphanede kesilerek bulunur)."""
    out = planla.turkce_satirlar(planla.cekim_listesi(seri, bolum, "shorts"))
    for s in planla.turkce_satirlar(planla.cekim_listesi(seri, bolum, "uzun")):
        if s not in out and not any(s[0] == k and _parca_mi(s[1], m) for k, m in out):
            out.append(s)
    return out


def _parca_mi(kisa, uzun):
    a, b = gemini_ses._tok(kisa), gemini_ses._tok(uzun)
    return bool(a) and any(b[i:i + len(a)] == a for i in range(len(b) - len(a) + 1))


def siradakiler(adet):
    """Her hattın sıradaki `adet` bölümü, yayın sırasına göre dönüşümlü (en yakın yayınlanacak önce)."""
    os.environ.pop("YAYIN", None)
    os.environ.pop("BOLUM", None)
    kayitlar = json.loads(bulut3d.KAYIT.read_text()) if bulut3d.KAYIT.exists() else []
    hatlar = [bulut3d.sira_ve_slotlar(kayitlar, h)[0][:adet] for h in bulut3d.HATLAR]
    out = []
    for i in range(adet):
        out += [h[i] for h in hatlar if i < len(h)]
    return out


def main(arg=None):
    p = argparse.ArgumentParser()
    p.add_argument("--adet", type=int, default=2)
    p.add_argument("--butce", type=int, default=5)
    p.add_argument("--bolum")
    p.add_argument("--zorla", action="store_true", help="saat penceresini yok say (elle deneme)")
    a = p.parse_args(arg)
    if not a.zorla and not gemini_ses.penceride():
        print("Gemini ses penceresi dışında (TR 22:00–10:30); bu çalışmada ses üretilmedi.")
        return 0
    seri = json.loads((SERI / "seri.json").read_text())
    ayar = gemini_ses.sesler(seri)
    yollar = [KOK / a.bolum] if a.bolum else siradakiler(a.adet)
    sayac = gemini_ses.Sayac(a.butce)
    tut_yol = gemini_ses.KUTUPHANE / "tutmayan.json"
    tutmayan = json.loads(tut_yol.read_text()) if tut_yol.exists() else {}
    rapor = []
    for yol in yollar:
        bolum = json.loads(Path(yol).read_text())
        satirlar = bolum_satirlari(seri, bolum)
        ad = Path(yol).stem
        if gemini_ses.bolum_sesleri(satirlar, ayar) is not None:
            rapor.append(f"{ad}: zaten hazır")
            continue
        if tutmayan.get(ad, 0) >= 2 and not a.bolum:  # iki gece tutmadıysa kota yakılmaz; edge-tts ile kalır
            rapor.append(f"{ad}: iki kez tutmadı, atlandı (edge-tts)")
            continue
        try:
            tamam = gemini_ses.hazirla(satirlar, ayar, sayac)
        except gemini_ses.KotaBitti as e:
            rapor.append(f"{ad}: kota/bütçe bitti ({str(e)[:80]}); sonraki gece")
            break
        except Exception as e:  # noqa: BLE001 — bir bölüm düşerse diğerleri denenir; render edge sesiyle sürer
            rapor.append(f"{ad}: hata {str(e)[:120]}")
            continue
        if not tamam:
            tutmayan[ad] = tutmayan.get(ad, 0) + 1
            gemini_ses.KUTUPHANE.mkdir(exist_ok=True)
            tut_yol.write_text(json.dumps(tutmayan, indent=0))
        rapor.append(f"{ad}: {'Gemini sesi hazır' if tamam else 'tutmadı (edge-tts ile çizilecek)'}")
    metin = "\n".join(["## Gece ses hazırlığı", *[f"- {r}" for r in rapor]] or ["sıra boş"])
    print(metin, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(metin + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
