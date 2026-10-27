"""3D bölümü YouTube'a elle, video başına onayla yükler. Varsayılan ve tek otomatik mod: private.

  ./venv/bin/python yayinla3d.py cikti3d/.../b001-shorts-XXXX.mp4
      -> yalnız denetler ve onay kodunu gösterir (hiçbir şey yüklemez)
  ./venv/bin/python yayinla3d.py <mp4> --onay <kod>
      -> PRIVATE olarak yükler
  Herkese açık/liste dışı: --gizlilik public --herkese-acik-onay "HERKESE-ACIK-<kod>"
      (ayrı, açık onay; zamanlanmış yayın desteklenmez)
Koşullar: rapor kalite_gecti=true, önizleme değil, aynı dosya/bölüm-profil daha önce yüklenmemiş.
Kimlik bilgileri yalnız ortam değişkeninden (YT_CLIENT_ID/SECRET/REFRESH_TOKEN) okunur.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
KAYIT = KOK / "yayin_kaydi.json"


def sha(yol):
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def denetle(mp4, kayitlar):
    rapor_yolu = Path(mp4).with_suffix(".rapor.json")
    if not rapor_yolu.exists():
        return None, ["kalite raporu yok"]
    rapor = json.loads(rapor_yolu.read_text())
    sorunlar = []
    if not rapor.get("kalite_gecti"):
        sorunlar.append("kalite kontrolünü geçmemiş")
    if rapor.get("onizleme"):
        sorunlar.append("önizleme kalitesinde; tam kalite render gerekli")
    kod = sha(mp4)[:10]
    for k in kayitlar:
        if k["sha"][:10] == kod:
            sorunlar.append(f"bu dosya zaten yüklendi: {k['video_id']}")
        if k["bolum"] == rapor["bolum"] and k["profil"] == rapor["profil"]:
            sorunlar.append(f"bu bölüm ({rapor['profil']}) zaten yüklendi: {k['video_id']}")
    return rapor | {"onay_kodu": kod}, sorunlar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4")
    ap.add_argument("--onay")
    ap.add_argument("--gizlilik", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--herkese-acik-onay")
    a = ap.parse_args()

    kayitlar = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    rapor, sorunlar = denetle(a.mp4, kayitlar)
    if sorunlar:
        print("YÜKLENEMEZ:", *sorunlar, sep="\n  - ")
        sys.exit(2)
    kod = rapor["onay_kodu"]
    if a.onay != kod:
        print(f"Denetim tamam. Yüklemek için (PRIVATE):\n  --onay {kod}")
        sys.exit(0 if a.onay is None else 3)
    acik_onay = a.gizlilik == "private" or a.herkese_acik_onay == f"HERKESE-ACIK-{kod}"
    if not acik_onay:
        print(f"'{a.gizlilik}' için ayrıca: --herkese-acik-onay HERKESE-ACIK-{kod}")
        sys.exit(3)

    from cocuk import youtube
    bolum = json.loads((KOK / rapor["bolum"]).read_text())
    meta = dict(bolum["youtube"])
    vid, durum = youtube.yukle(a.mp4, meta, youtube.erisim_anahtari(), gizlilik=a.gizlilik,
                               acik_onay=acik_onay, shorts=rapor["profil"] == "shorts",
                               sentetik=False)  # el yapımı 3D çizgi film; gerçekçi sentetik içerik değil
    kayitlar.append({"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "sha": sha(a.mp4), "bolum": rapor["bolum"], "profil": rapor["profil"],
                     "video_id": vid, "durum": durum})
    KAYIT.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=1))
    print("yüklendi:", vid, durum)
    if durum.get("privacyStatus") != a.gizlilik:
        print(f"UYARI: YouTube durumu '{durum.get('privacyStatus')}' (istenen '{a.gizlilik}')")
        sys.exit(4)


if __name__ == "__main__":
    main()
