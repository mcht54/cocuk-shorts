"""Tek çalıştırma: tür seç -> senaryo -> video -> kalite kontrolü -> (izinliyse) YouTube -> geçmiş.

Ortam değişkenleri (GitHub Secrets/Variables):
  GEMINI_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  YAYIN=acik      -> YouTube'a yükle (varsayılan: kapalı; video yalnız üretilip saklanır)
  YT_GIZLILIK     -> private (varsayılan) / unlisted / public
  YT_HERKESE_ACIK_ONAY=evet -> private dışı gizlilik için ayrı, açık onay (yoksa yükleme reddedilir)
  CF_GUNLUK_NORON, GEMINI_GUNLUK_CAGRI -> ücretsiz kota için günlük üst sınırlar
Kullanım: python calistir.py [--senaryo dosya.json] [--tur masal|egitici|hayvan]
Çıkış kodu 0 değilse çalıştırma başarısızdır (GitHub e-posta ile bildirir).
"""
import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cocuk import gorsel, kalite, video
from cocuk import senaryo as senaryo_mod

KOK = Path(__file__).resolve().parent
GECMIS = Path(os.environ.get("GECMIS_DOSYASI", KOK / "gecmis.json"))
CIKTI = KOK / "cikti"
KAYIT = KOK / "kayit"
TURLER = list(senaryo_mod.TURLER)
DENEME = int(os.environ.get("EN_FAZLA_DENEME", 2))


def log(*parca):
    satir = f"[{datetime.now(timezone.utc):%H:%M:%S}] " + " ".join(str(p) for p in parca)
    print(satir, flush=True)
    KAYIT.mkdir(exist_ok=True)
    with open(KAYIT / "calisma.log", "a") as f:
        f.write(satir + "\n")


def ozet(metin):
    """GitHub Actions çalıştırma sayfasındaki özet."""
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")


def bugun_kullanim(gecmis):
    bugun = datetime.now(timezone.utc).date().isoformat()
    kayitlar = [g for g in gecmis if g["tarih"][:10] == bugun]
    return (sum(g.get("cf_noron", 0) for g in kayitlar),
            sum(g.get("gemini_cagri", 0) for g in kayitlar))


def tur_sec(gecmis, izlenme):
    """İzlenmesi yüksek türe daha çok sıra ver; hiçbir tür %20'nin altına düşmesin."""
    simdi = datetime.now(timezone.utc)
    ortalama = {}
    for t in TURLER:
        degerler = [izlenme[g["video_id"]] for g in gecmis[-45:]
                    if g["tur"] == t and g.get("video_id") in izlenme
                    and simdi - datetime.fromisoformat(g["tarih"]) > timedelta(days=2)]
        ortalama[t] = sum(degerler) / len(degerler) if len(degerler) >= 3 else None
    bilinen = [v for v in ortalama.values() if v is not None]
    taban = (sum(bilinen) / len(bilinen)) if bilinen else 1
    agirlik = {t: (ortalama[t] if ortalama[t] is not None else taban) + 1 for t in TURLER}
    toplam = sum(agirlik.values())
    agirlik = {t: max(0.2, a / toplam) for t, a in agirlik.items()}
    basarili = [g for g in gecmis if g.get("durum") in ("yayinlandi", "uretildi")]
    if basarili:  # art arda aynı tür olmasın
        agirlik[basarili[-1]["tur"]] *= 0.3
    log("tür ağırlıkları:", {t: round(a, 2) for t, a in agirlik.items()})
    return random.choices(TURLER, weights=[agirlik[t] for t in TURLER])[0]


def yayin_kilitli(gecmis):
    """Daha önce YouTube videoyu özel olarak kilitlediyse (API denetimi yok) tekrar yükleme."""
    for g in reversed(gecmis):
        if g.get("durum") == "yayinlandi":
            return False
        if g.get("durum") == "kilitli":
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--senaryo", help="Gemini yerine hazır senaryo JSON'u kullan")
    ap.add_argument("--tur", choices=TURLER)
    arg = ap.parse_args()

    gecmis = json.loads(GECMIS.read_text()) if GECMIS.exists() else []
    yayin = os.environ.get("YAYIN", "kapali") == "acik"
    cf_bugun, gemini_bugun = bugun_kullanim(gecmis)
    log(f"başlangıç: yayın={'açık' if yayin else 'kapalı'}, bugün cloudflare≈{cf_bugun:.0f} nöron, "
        f"gemini {gemini_bugun} çağrı")

    if yayin and yayin_kilitli(gecmis):
        log("UYARI: önceki yükleme YouTube tarafından özel olarak kilitlendi (API denetimi onaylanmamış). "
            "Bu çalıştırmada yükleme yapılmayacak; denetim onaylanınca gecmis.json'daki 'kilitli' "
            "kaydını silin.")
        yayin = False

    anahtar, izlenme = None, {}
    if yayin:
        from cocuk import youtube
        anahtar = youtube.erisim_anahtari()
        idler = [g["video_id"] for g in gecmis[-45:] if g.get("video_id")]
        if idler:
            try:
                izlenme = youtube.izlenmeler(idler, anahtar)
            except Exception as e:  # istatistik okunamazsa üretim yine sürer
                log("izlenme okunamadı:", e)
            for g in gecmis:
                if g.get("video_id") in izlenme:
                    g["izlenme"] = izlenme[g["video_id"]]

    hazir = json.loads(Path(arg.senaryo).read_text()) if arg.senaryo else None
    tur = arg.tur or (hazir or {}).get("tur") or os.environ.get("TUR") or tur_sec(gecmis, izlenme)
    log("seçilen tür:", tur)
    senaryo_mod.GUNLUK_SINIR = int(os.environ.get("GEMINI_GUNLUK_CAGRI", 30)) - gemini_bugun

    kayit = {"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tur": tur,
             "durum": "hata", "cf_noron": 0, "gemini_cagri": 0}
    kota = gorsel.Kota(cf_bugun=cf_bugun)
    basari = False
    try:
        for deneme in range(1, DENEME + 1):
            log(f"--- deneme {deneme}/{DENEME}")
            if hazir:
                s = dict(hazir, tur=tur)
            else:
                s = senaryo_mod.yaz(tur, [g["konu"] for g in gecmis if g.get("konu")])
            kayit.update({"konu": s.get("konu", s["baslik"]), "baslik": s["baslik"]})
            log("senaryo:", s["baslik"])
            gecici = Path(tempfile.mkdtemp(prefix="cocuk-"))
            try:
                mp4 = gecici / "video.mp4"
                rapor = video.uret(s, mp4, gecici / "is", kota)
                tamam, hatalar, olcum = kalite.denetle(mp4, rapor)
                kayit["kalite"] = {"tamam": tamam, "hatalar": hatalar, **olcum}
                log("kalite:", "GEÇTİ" if tamam else "KALDI", json.dumps(olcum, ensure_ascii=False))
                if not tamam:
                    for h in hatalar:
                        log("  -", h)
                    continue
                kayit["sure"] = rapor["sure"]
                if yayin:
                    from cocuk import youtube
                    istenen = os.environ.get("YT_GIZLILIK", "private")
                    vid, durum = youtube.yukle(
                        mp4, s, anahtar, gizlilik=istenen,
                        acik_onay=os.environ.get("YT_HERKESE_ACIK_ONAY") == "evet")
                    kayit["video_id"] = vid
                    kayit["youtube"] = durum
                    log("yüklendi:", f"https://youtube.com/shorts/{vid}", durum)
                    if durum.get("privacyStatus") != istenen:
                        kayit["durum"] = "kilitli"
                        raise RuntimeError(
                            f"YouTube videoyu '{durum.get('privacyStatus')}' yaptı (istenen '{istenen}'). "
                            "API projesi denetimden geçmemiş olabilir; yükleme durduruldu.")
                    kayit["durum"] = "yayinlandi"
                else:
                    CIKTI.mkdir(exist_ok=True)
                    hedef = CIKTI / f"{datetime.now():%Y%m%d-%H%M}-{tur}.mp4"
                    shutil.move(mp4, hedef)
                    kayit["durum"] = "uretildi"
                    kayit["dosya"] = hedef.name
                    log("yayın kapalı; video kaydedildi:", hedef)
                basari = True
                break
            finally:
                shutil.rmtree(gecici, ignore_errors=True)
    except Exception as e:
        kayit["hata"] = f"{type(e).__name__}: {e}"
        log("HATA:", kayit["hata"])
        log(traceback.format_exc())
    finally:
        kayit["cf_noron"] = round(kota.cf_kullanilan, 1)
        kayit["gemini_cagri"] = senaryo_mod.CAGRI
        if not basari and "hata" not in kayit:
            kayit["hata"] = f"{DENEME} denemede kalite kontrolü geçilemedi"
        gecmis.append(kayit)
        GECMIS.write_text(json.dumps(gecmis, ensure_ascii=False, indent=1))
        ozet(f"### {kayit['durum'].upper()} — {kayit.get('baslik', tur)}\n"
             + (f"- YouTube: https://youtube.com/shorts/{kayit['video_id']}\n" if kayit.get("video_id") else "")
             + (f"- Hata: {kayit['hata']}\n" if kayit.get("hata") else "")
             + f"- Görseller: {kayit.get('kalite', {}).get('gorsel_kaynaklari')}\n"
             + f"- Kota: cloudflare≈{kayit['cf_noron']} nöron, gemini {kayit['gemini_cagri']} çağrı\n")
    sys.exit(0 if basari else 1)


if __name__ == "__main__":
    main()
