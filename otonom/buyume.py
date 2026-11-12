"""Haftalık büyüme işi (buyume.yml): yüklenmiş videoları çalma listelerine ekler (eksikse) ve izlenme
raporu yazar: hangi bölüm/tür tutuyor. Geniş YouTube izni (yetki_al.py --buyume) gerekir; yoksa raporlar.

Rapor otonom/izlenme.json'a yazılır (haftalık onay e-postası ve sonraki kararlar için).
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from cocuk import youtube

KOK = Path(__file__).resolve().parent.parent
KAYIT = KOK / "yayin_kaydi.json"
RAPOR = KOK / "otonom" / "izlenme.json"


def ozet(metin):
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")
    print(metin, flush=True)


def liste_adi(k):
    if k.get("profil") == "shorts":
        return "Fındık ile Pamuk | Tüm Bölümler"
    if k.get("tur") == "karisik":
        return "Uyku Öncesi Masallar | Fındık ile Pamuk"
    return "Fındık ile Pamuk | Uzun Videolar"


def main():
    kayit = json.loads(KAYIT.read_text())
    yuklenen = [k for k in kayit if k.get("durum") == "yuklendi" and k.get("video_id")]
    anahtar = youtube.erisim_anahtari()
    eklenen = 0
    for k in sorted(yuklenen, key=lambda k: k.get("yayin_zamani") or k["tarih"]):
        if youtube.listeye_ekle(k["video_id"], liste_adi(k), anahtar):
            eklenen += 1
    ozet(f"Çalma listeleri: {eklenen}/{len(yuklenen)} video listede"
         + ("" if eklenen else " (izin yalnız yükleme olabilir: yetki_al.py --buyume)"))
    izl = youtube.izlenmeler([k["video_id"] for k in yuklenen], anahtar)
    gizlilik = {}
    ids = [k["video_id"] for k in yuklenen]
    for i in range(0, len(ids), 50):
        r = youtube.requests.get(f"{youtube.API}/videos", timeout=30, headers={"Authorization": f"Bearer {anahtar}"},
                                 params={"part": "status", "id": ",".join(ids[i:i + 50])})
        if r.ok:
            for v in r.json().get("items", []):
                gizlilik[v["id"]] = v["status"].get("privacyStatus") + (
                    f" ({v['status']['publishAt'][:16]})" if v["status"].get("publishAt") else "")
    satirlar = []
    for k in yuklenen:
        bolum = k["bolum"]
        ad = bolum
        if bolum.endswith(".json") and (KOK / bolum).exists():
            ad = json.loads((KOK / bolum).read_text())["baslik"]
        elif k.get("tur"):
            ad = f"derleme ({k['tur']})"
        satirlar.append({"video_id": k["video_id"], "profil": k.get("profil"), "ad": ad,
                         "yayin": (k.get("yayin_zamani") or k["tarih"])[:10], "izlenme": izl.get(k["video_id"]),
                         "durum": gizlilik.get(k["video_id"], "silinmiş?")})
    satirlar.sort(key=lambda s: -(s["izlenme"] or 0))
    RAPOR.write_text(json.dumps({"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "videolar": satirlar}, ensure_ascii=False, indent=1))
    toplam = sum(s["izlenme"] or 0 for s in satirlar)
    ozet(f"\n### İzlenmeler (toplam {toplam})\n| Video | Tür | Yayın | Durum | İzlenme |\n|---|---|---|---|---|")
    for s in satirlar:
        ozet(f"| {s['ad']} | {s['profil']} | {s['yayin']} | {s['durum']} | {s['izlenme']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
