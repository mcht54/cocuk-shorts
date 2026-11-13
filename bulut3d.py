"""Bulutta (GitHub Actions) günlük 3D bölüm: sıradaki bölüm -> üret -> kalite -> (izinliyse) yükle.

Ortam: YAYIN=acik ise yükler (varsayılan kapalı). YT_GIZLILIK varsayılan private; private dışı için
ayrıca YT_HERKESE_ACIK_ONAY=evet. Kimlik: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN.
Kayıt: yayin_kaydi.json (repoya yazılır; aynı bölüm iki kez yüklenmez). Çıkış kodu 0 = başarı.

Parçalı bulut üretimi (gunluk3d.yml + ciz.yml):
  python bulut3d.py sec                       -> sıradaki bölüm + yayın saati (GITHUB_OUTPUT)
  python bulut3d.py yukle <bolum> [<slot>]     -> ciz.yml'nin ürettiği raporu işler, izinliyse yükler
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from otonom import seo, takvim

KOK = Path(__file__).resolve().parent
SERI = KOK / "seri" / "findik-ile-pamuk"
KAYIT = KOK / "yayin_kaydi.json"
PROFIL = os.environ.get("PROFIL", "shorts")


# Hatlar (2026-11-13 kullanıcı: günde 2 Shorts, biri İngilizce eğitim): aynı seri, aynı karakterler.
HATLAR = {
    "masal_shorts": {"desen": "b*.json", "liste": "Fındık ile Pamuk | Tüm Bölümler",
                     "liste_aciklama": "Fındık ile Pamuk'un bütün masalları sırayla. 3-7 yaş için Türkçe 3D çizgi film.",
                     "meta": seo.masal_shorts, "sira": "yayin_sirasi.json"},
    "ingilizce_shorts": {"desen": "e*.json", "liste": "Çocuklar için İngilizce | Fındık ile Pamuk",
                         "liste_aciklama": "Fındık ile Pamuk ile her gün yeni İngilizce kelimeler: renkler, sayılar, "
                                           "hayvanlar, selamlaşma. Okul öncesi ve ilkokul için tekrarlı İngilizce dersleri.",
                         "meta": seo.ingilizce_shorts, "sira": None},
}


def bolum_hatti(yol):
    return "ingilizce_shorts" if Path(yol).name.startswith("e") else "masal_shorts"


def meta_hazirla(bolum, hat="masal_shorts", onceki_basliklar=()):
    """Bölüm dosyasından yükleme bilgisi (otonom.seo) + SEO denetimi. (meta, sorunlar)."""
    meta = HATLAR[hat]["meta"](bolum)
    sorun = seo.denetle(meta, shorts=True, onceki_basliklar=onceki_basliklar)
    if "başlık daha önce yüklenen bir videoyla aynı" in sorun:
        meta["baslik"] = f"{meta['baslik'][:80]} ({bolum.get('bolum_no')})"
        sorun = seo.denetle(meta, shorts=True, onceki_basliklar=onceki_basliklar)
    return meta, sorun


def ozet(metin):
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")
    print(metin, flush=True)


def sira_ve_slotlar(kayitlar, hat="masal_shorts"):
    """(sıradaki bölümler, doldurulacak yayın saatleri); takvim doluysa slotlar boş liste."""
    h = HATLAR[hat]
    # yalnız yüklenenler tamamlanmış sayılır: onay öncesi denemeler bölüm tüketmesin
    yapilan = {(k["bolum"], k["profil"]) for k in kayitlar if k.get("durum") == "yuklendi"}
    # kalite kontrolünü iki kez geçemeyen bölüm sırayı kilitlemesin: atlanır (kayıtta görünür)
    kalan = {}
    for k in kayitlar:
        if k.get("durum") == "kalite_kaldi" and k["profil"] == PROFIL:
            kalan[k["bolum"]] = kalan.get(k["bolum"], 0) + 1
    bolumler = sorted(SERI.glob("bolumler/" + h["desen"]))
    # yayin_sirasi.json varsa önce o sıra (ör. macera mini dizisi art arda), kalanlar numara sırasıyla
    sira_dosyasi = SERI / h["sira"] if h["sira"] else None
    if sira_dosyasi and sira_dosyasi.exists():
        oncelik = [SERI / "bolumler" / f"{ad}.json" for ad in json.loads(sira_dosyasi.read_text())]
        oncelik = [b for b in oncelik if b.exists()]
        bolumler = oncelik + [b for b in bolumler if b not in oncelik]
    sira = [b for b in bolumler if (str(b.relative_to(KOK)), PROFIL) not in yapilan
            and kalan.get(str(b.relative_to(KOK)), 0) < 2]
    if os.environ.get("BOLUM"):
        sira = [KOK / os.environ["BOLUM"]]
    # yayın açıksa takvimdeki boş saatler doldurulur (1 hafta önceden, zamanlanmış); kapalıysa tek deneme
    if os.environ.get("YAYIN") == "acik" and PROFIL == "shorts" and not os.environ.get("BOLUM"):
        bos = takvim.bos_slotlar(hat, kayitlar)[:int(os.environ.get("EN_COK_SLOT", "2"))]
    else:
        bos = [None]
    return sira, bos


def hat_sec(kayitlar):
    """HAT verilmemişse: en yakın boş yayın saati olan ve stoğu bulunan hat (iki hat da dolu kalsın)."""
    if os.environ.get("HAT"):
        return os.environ["HAT"]
    if os.environ.get("BOLUM"):
        return bolum_hatti(os.environ["BOLUM"])
    adaylar = []
    for hat in HATLAR:
        sira, bos = sira_ve_slotlar(kayitlar, hat)
        if sira and bos and bos[0] is not None:
            adaylar.append((bos[0], hat))
    return min(adaylar)[1] if adaylar else "masal_shorts"


def sec():
    kayitlar = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    hat = hat_sec(kayitlar)
    sira, bos = sira_ve_slotlar(kayitlar, hat)
    ozet(f"Hat: {hat}")
    if not sira:
        ozet(f"{hat}: üretilecek yeni bölüm kalmadı. seri/findik-ile-pamuk/bolumler'e bölüm eklenmeli.")
    elif not bos:
        ozet("Takvim dolu: önümüzdeki hafta için tüm Shorts zamanlanmış.")
    bolum = str(sira[0].relative_to(KOK)) if sira and bos else ""
    slot = bos[0].isoformat() if bos and bos[0] else ""
    if bolum:
        ozet(f"Seçilen: {bolum}" + (f", yayın {slot}" if slot else ""))
    cikti = os.environ.get("GITHUB_OUTPUT")
    if cikti:
        with open(cikti, "a") as f:
            f.write(f"bolum={bolum}\nslot={slot}\nhat={hat}\n")
    return 0


def main():
    kayitlar = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    sira, bos = sira_ve_slotlar(kayitlar, hat_sec(kayitlar))
    if not sira:
        ozet("Üretilecek yeni bölüm kalmadı. seri/findik-ile-pamuk/bolumler'e bölüm eklenmeli.")
        return 1
    if not bos:
        ozet("Takvim dolu: önümüzdeki hafta için tüm Shorts zamanlanmış.")
        return 0
    basari = 0
    for slot in bos:
        # bir bölüm kaliteyi geçemezse aynı slot için sıradakini dene (gün boş geçmesin)
        for bolum in sira[:2]:
            if bolum_isle(bolum, kayitlar, slot) == 0:
                sira.remove(bolum)
                basari += 1
                break
            sira.remove(bolum)
        if not sira:
            break
    return 0 if basari else 1


def bolum_isle(bolum, kayitlar, slot=None):
    ozet(f"### {bolum.name} ({PROFIL})")

    komut = [sys.executable, str(KOK / "uret3d.py"), "--bolum", str(bolum), "--profil", PROFIL,
             "--ornekleme", os.environ.get("ORNEKLEME", "4"), "--olcek", os.environ.get("OLCEK", "67")]
    if PROFIL == "uzun":
        komut.append("--prototip")
    r = subprocess.run(komut)
    return sonuc_isle(bolum, kayitlar, slot, r.returncode)


def sonuc_isle(bolum, kayitlar, slot=None, kod=0):
    """Üretim raporunu okur; geçtiyse (izinliyse) yükler. Kayda yazar. 0 = yüklendi/üretildi."""
    raporlar = sorted((KOK / "cikti3d" / "findik-ile-pamuk").glob(f"{bolum.stem}-{PROFIL}-2*.rapor.json"))
    if kod != 0 or not raporlar or not json.loads(raporlar[-1].read_text()).get("kalite_gecti"):
        ozet("Üretim ya da kalite kontrolü BAŞARISIZ; video yayımlanmadı.")
        hatalar = json.loads(raporlar[-1].read_text())["hatalar"] if raporlar else ["üretim hatası"]
        for h in hatalar:
            ozet(f"- {h}")
        if os.environ.get("YAYIN") == "acik":  # deneme çalıştırmaları atlama sayacına girmez
            kayitlar.append({"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "bolum": str(bolum.relative_to(KOK)), "profil": PROFIL,
                             "durum": "kalite_kaldi", "hatalar": hatalar[:5]})
            KAYIT.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=1))
        return 1
    rapor = json.loads(raporlar[-1].read_text())
    mp4 = KOK / rapor["video"]
    ozet(f"Kalite GEÇTİ: {rapor['olcum']['sure']} sn, {rapor['olcum']['cozunurluk']}, "
         f"üretim {rapor['uretim_suresi_sn']} sn")

    hat = bolum_hatti(bolum)
    kayit = {"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "bolum": str(bolum.relative_to(KOK)), "profil": PROFIL, "durum": "uretildi", "hat": hat}
    meta, sorun = meta_hazirla(json.loads(bolum.read_text()), hat,
                               [k.get("baslik") for k in kayitlar if k.get("durum") == "yuklendi"])
    ozet(f"Başlık: {meta['baslik']}")
    for s in sorun:
        ozet(f"- SEO uyarısı: {s}")
    if os.environ.get("YAYIN") == "acik":
        from cocuk import youtube
        gizlilik = os.environ.get("YT_GIZLILIK", "private")
        publish, zaman = takvim.yukleme_zamani(slot) if slot else (None, datetime.now(timezone.utc))
        vid, durum = youtube.yukle(mp4, meta, youtube.erisim_anahtari(), gizlilik=gizlilik,
                                   acik_onay=os.environ.get("YT_HERKESE_ACIK_ONAY") == "evet",
                                   shorts=PROFIL == "shorts", sentetik=False, yayin_zamani=publish,
                                   hazir_aciklama=meta.get("hazir_aciklama", False))
        kayit.update(durum="yuklendi", video_id=vid, youtube=durum, yayin_zamani=zaman.isoformat(timespec="seconds"),
                     baslik=meta["baslik"])
        if youtube.listeye_ekle(vid, HATLAR[hat]["liste"], youtube.erisim_anahtari(), HATLAR[hat]["liste_aciklama"]):
            kayit["liste"] = "eklendi"
        ozet(f"YouTube: https://youtube.com/shorts/{vid} — {durum}"
             + (f" — yayın {zaman:%Y-%m-%d %H:%M} UTC" if publish else ""))
        if not publish and durum.get("privacyStatus") != gizlilik:
            ozet(f"UYARI: YouTube durumu '{durum.get('privacyStatus')}' (istenen '{gizlilik}'). "
                 "API denetimi onaylanmamış olabilir.")
    else:
        ozet("Yayın kapalı (YAYIN != acik): video yalnız üretildi, Actions 'Artifacts' altında indirilebilir.")
    kayitlar.append(kayit)
    KAYIT.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sec":
        sys.exit(sec())
    if len(sys.argv) > 2 and sys.argv[1] == "yukle":
        kayitlar = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
        slot = datetime.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
        sys.exit(sonuc_isle(KOK / sys.argv[2], kayitlar, slot))
    sys.exit(main())
