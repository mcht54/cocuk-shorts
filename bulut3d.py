"""Bulutta (GitHub Actions) günlük 3D bölüm: sıradaki bölüm -> üret -> kalite -> (izinliyse) yükle.

Ortam: YAYIN=acik ise yükler (varsayılan kapalı). YT_GIZLILIK varsayılan private; private dışı için
ayrıca YT_HERKESE_ACIK_ONAY=evet. Kimlik: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN.
Kayıt: yayin_kaydi.json (repoya yazılır; aynı bölüm iki kez yüklenmez). Çıkış kodu 0 = başarı.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
SERI = KOK / "seri" / "findik-ile-pamuk"
KAYIT = KOK / "yayin_kaydi.json"
PROFIL = os.environ.get("PROFIL", "shorts")


def ozet(metin):
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")
    print(metin, flush=True)


def main():
    kayitlar = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    # yalnız yüklenenler tamamlanmış sayılır: onay öncesi denemeler bölüm tüketmesin
    yapilan = {(k["bolum"], k["profil"]) for k in kayitlar if k.get("durum") == "yuklendi"}
    bolumler = sorted(SERI.glob("bolumler/b*.json"))
    sira = [b for b in bolumler if (str(b.relative_to(KOK)), PROFIL) not in yapilan]
    if os.environ.get("BOLUM"):
        sira = [KOK / os.environ["BOLUM"]]
    if not sira:
        ozet("Üretilecek yeni bölüm kalmadı. seri/findik-ile-pamuk/bolumler'e bölüm eklenmeli.")
        return 0
    bolum = sira[0]
    ozet(f"### {bolum.name} ({PROFIL})")

    komut = [sys.executable, str(KOK / "uret3d.py"), "--bolum", str(bolum), "--profil", PROFIL,
             "--ornekleme", os.environ.get("ORNEKLEME", "4"), "--olcek", os.environ.get("OLCEK", "67")]
    if PROFIL == "uzun":
        komut.append("--prototip")
    r = subprocess.run(komut)
    raporlar = sorted((KOK / "cikti3d" / "findik-ile-pamuk").glob(f"{bolum.stem}-{PROFIL}-2*.rapor.json"))
    if r.returncode != 0 or not raporlar:
        ozet("Üretim ya da kalite kontrolü BAŞARISIZ; video yayımlanmadı.")
        if raporlar:
            for h in json.loads(raporlar[-1].read_text())["hatalar"]:
                ozet(f"- {h}")
        return 1
    rapor = json.loads(raporlar[-1].read_text())
    mp4 = KOK / rapor["video"]
    ozet(f"Kalite GEÇTİ: {rapor['olcum']['sure']} sn, {rapor['olcum']['cozunurluk']}, "
         f"üretim {rapor['uretim_suresi_sn']} sn")

    kayit = {"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "bolum": str(bolum.relative_to(KOK)), "profil": PROFIL, "durum": "uretildi"}
    if os.environ.get("YAYIN") == "acik":
        from cocuk import youtube
        gizlilik = os.environ.get("YT_GIZLILIK", "private")
        meta = json.loads(bolum.read_text())["youtube"]
        vid, durum = youtube.yukle(mp4, meta, youtube.erisim_anahtari(), gizlilik=gizlilik,
                                   acik_onay=os.environ.get("YT_HERKESE_ACIK_ONAY") == "evet",
                                   shorts=PROFIL == "shorts", sentetik=False)
        kayit.update(durum="yuklendi", video_id=vid, youtube=durum)
        ozet(f"YouTube: https://youtube.com/shorts/{vid} — {durum}")
        if durum.get("privacyStatus") != gizlilik:
            ozet(f"UYARI: YouTube durumu '{durum.get('privacyStatus')}' (istenen '{gizlilik}'). "
                 "API denetimi onaylanmamış olabilir.")
    else:
        ozet("Yayın kapalı (YAYIN != acik): video yalnız üretildi, Actions 'Artifacts' altında indirilebilir.")
    kayitlar.append(kayit)
    KAYIT.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
