"""Merak Arşivi günlük yayın: sıradaki senaryo -> üret -> kalite kontrolü -> (izinliyse) yükle -> kayıt.

Kullanım: python -m merak.yayinla --profil shorts|uzun [--konu KİMLİK --senaryo kisa1] [--yayin hayir]
Ortam: YAYIN=acik ise yükler. Gizlilik MERAK_GIZLILIK (varsayılan private); private dışı için
YT_HERKESE_ACIK_ONAY=evet. Kimlik: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN (Merak Arşivi kanalının).
Kayıt merak/kayit.json; aynı senaryo iki kez yüklenmez, iki kez kalite kalan atlanır. Çıkış 0 = başarı.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from merak import uret

KOK = Path(__file__).resolve().parent
KONULAR = KOK / "konular"
KAYIT = KOK / "kayit.json"
SINIR = {"uzun": (300, 1500, (1920, 1080)), "shorts": (20, 89, (1080, 1920))}


def ozet(metin):
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")
    print(metin, flush=True)


def kayitlar():
    return json.loads(KAYIT.read_text()) if KAYIT.exists() else []


def kaydet(k):
    hepsi = kayitlar()
    hepsi.append(k)
    KAYIT.write_text(json.dumps(hepsi, ensure_ascii=False, indent=1))


def _konular():
    """Konular eklenme sırasıyla (kaynak.json tarihi); reddedilenler hariç."""
    out = []
    for d in KONULAR.glob("*"):
        if (d / "kaynak.json").exists() and not (d / "reddedildi").exists():
            out.append((json.loads((d / "kaynak.json").read_text()).get("tarih", ""), d.name))
    return [k for _, k in sorted(out)]


def sira(profil):
    """Yayınlanmayı bekleyen (konu, senaryo) listesi, öncelik sırasıyla."""
    k = kayitlar()
    yapilan = {(x["konu"], x["senaryo"]) for x in k if x.get("durum") == "yuklendi"}
    kalan = {}
    for x in k:
        if x.get("durum") == "kalite_kaldi":
            kalan[(x["konu"], x["senaryo"])] = kalan.get((x["konu"], x["senaryo"]), 0) + 1
    uygun = lambda kid, ad: (kid, ad) not in yapilan and kalan.get((kid, ad), 0) < 2  # noqa: E731
    konular = _konular()
    if profil == "uzun":
        return [(kid, "uzun") for kid in konular if (KONULAR / kid / "uzun.json").exists() and uygun(kid, "uzun")]
    # Shorts: uzun videosu yayınlanmış konulardan, konular arasında dönüşümlü (art arda aynı konu olmasın)
    yayinda = [kid for kid in konular if (kid, "uzun") in yapilan] or konular
    havuz = {kid: sorted(p.stem for p in (KONULAR / kid).glob("kisa*.json") if uygun(kid, p.stem))
             for kid in konular}
    once = [kid for kid in yayinda if havuz[kid]] + [kid for kid in konular if kid not in yayinda and havuz[kid]]
    son_konu = next((x["konu"] for x in reversed(k) if x.get("profil") == "shorts" and x.get("durum") == "yuklendi"), None)
    out = []
    while any(havuz[kid] for kid in once):
        for kid in sorted(once, key=lambda c: c == son_konu):
            if havuz[kid]:
                out.append((kid, havuz[kid].pop(0)))
    return out


def denetle(mp4, profil):
    hatalar = []
    alt, ust, boyut = SINIR[profil]
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(mp4)], capture_output=True, text=True)
    try:
        v = json.loads(r.stdout)
        sure = float(v["format"]["duration"])
        cozunurluk = (v["streams"][0]["width"], v["streams"][0]["height"])
    except (ValueError, KeyError, IndexError):
        return [f"video okunamadı: {r.stderr[:200]}"], {}
    if not alt <= sure <= ust:
        hatalar.append(f"süre {sure:.1f} sn, {alt}-{ust} olmalı")
    if cozunurluk != boyut:
        hatalar.append(f"çözünürlük {cozunurluk}, beklenen {boyut}")
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(mp4), "-vf",
                        "blackdetect=d=2.5:pix_th=0.08,freezedetect=n=0.002:d=8", "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    siyah = re.findall(r"black_duration:([\d.]+)", r.stderr)
    donuk = re.findall(r"freeze_duration: ([\d.]+)", r.stderr)
    ses = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    if siyah:
        hatalar.append(f"{len(siyah)} siyah aralık (en uzun {max(map(float, siyah)):.1f} sn)")
    if donuk:
        hatalar.append(f"{len(donuk)} donuk aralık (en uzun {max(map(float, donuk)):.1f} sn)")
    ortalama = float(ses.group(1)) if ses else None
    if ortalama is None or ortalama < -35:
        hatalar.append(f"ses yok ya da çok kısık ({ortalama} dB)")
    return hatalar, {"sure": round(sure, 1), "cozunurluk": f"{cozunurluk[0]}x{cozunurluk[1]}", "ses_db": ortalama}


def isle(kid, ad, profil, yayin):
    ozet(f"### {kid} / {ad} ({profil})")
    kayit = {"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"), "konu": kid, "senaryo": ad,
             "profil": profil}
    try:
        sonuc = uret.uret(kid, ad)
        hatalar, olcum = denetle(sonuc["video"], profil)
    except Exception as e:  # üretim hatası da kalite kalması sayılır (sonsuz döngü olmasın)
        hatalar, olcum, sonuc = [f"üretim hatası: {e}"[:300]], {}, None
    if hatalar:
        ozet("Kalite kontrolü GEÇMEDİ, yayımlanmadı:\n" + "\n".join(f"- {h}" for h in hatalar))
        if yayin:
            kaydet({**kayit, "durum": "kalite_kaldi", "hatalar": hatalar[:5]})
        return 1
    ozet(f"Kalite GEÇTİ: {olcum}")
    kayit.update(durum="uretildi", olcum=olcum)
    if yayin:
        from cocuk import youtube
        from derleme import kapak_yukle
        s = json.loads((KONULAR / kid / f"{ad}.json").read_text())
        gizlilik = os.environ.get("MERAK_GIZLILIK", "private")
        anahtar = youtube.erisim_anahtari()
        meta = {"baslik": s["baslik"], "aciklama": sonuc["aciklama"], "etiketler": s.get("etiketler", [])}
        vid, durum = youtube.yukle(sonuc["video"], meta, anahtar, gizlilik=gizlilik,
                                   acik_onay=os.environ.get("YT_HERKESE_ACIK_ONAY") == "evet",
                                   shorts=profil == "shorts", sentetik=False, cocuklar=False,
                                   hazir_aciklama=True)
        kayit.update(durum="yuklendi", video_id=vid, youtube=durum)
        ozet(f"YouTube: https://youtube.com/watch?v={vid} — {durum}")
        if sonuc.get("kapak"):
            kod, metin = kapak_yukle(vid, sonuc["kapak"], anahtar)
            kayit["kapak"] = "yuklendi" if kod == 200 else f"yuklenemedi ({kod})"
            ozet("Kapak yüklendi." if kod == 200 else f"Kapak yüklenemedi ({kod}): {metin}")
    else:
        ozet("Yayın kapalı: video yalnız üretildi (Actions 'Artifacts').")
    kaydet(kayit) if yayin else None
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profil", choices=["shorts", "uzun"], required=True)
    ap.add_argument("--konu")
    ap.add_argument("--senaryo")
    ap.add_argument("--yayin", default="otomatik")
    a = ap.parse_args()
    yayin = a.yayin != "hayir" and os.environ.get("YAYIN") == "acik"
    adaylar = [(a.konu, a.senaryo or "uzun")] if a.konu else sira(a.profil)
    if not adaylar:
        ozet(f"Yayınlanacak {a.profil} kalmadı: stok doldurma işi (stok.yml) yeni konu yazmalı.")
        return 1
    for kid, ad in adaylar[:2]:  # biri kalırsa aynı gün sıradakini dene
        if isle(kid, ad, a.profil, yayin) == 0:
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
