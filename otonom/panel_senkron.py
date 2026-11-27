"""Panel "İçerik takvimi" senkronu (anahtarsız): GitHub Actions OIDC belgesiyle Mchttasarım paneline Minik Masal Evi takvimini gönderir,
paneldeki bekleyen replik düzenlemelerini sıradaki (henüz yüklenmemiş) bölümlere uygular. Panelde GitHub anahtarı yoktur.

Kural: yüklenmiş bölüm değişmez; düzenlenen bölüm render öncesi denetimden (cocuk3d.bolum_denetle) geçmezse geri alınır ve reddedilir.
Kullanım (Actions'ta, `permissions: id-token: write`): python -m otonom.panel_senkron al | son
Panel erişilemezse akış BOZULMAZ (çıkış 0)."""
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

from cocuk3d import bolum_denetle

KOK = Path(__file__).resolve().parent.parent
SERI = KOK / "seri" / "findik-ile-pamuk"
KAYIT = KOK / "yayin_kaydi.json"
PANEL = os.environ.get("PANEL_URL", "https://panel.mchttasarim.com.tr")
AUD = "mchttasarim-panel-icerik"
KANAL = "minik_masal"
ONAY = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "panel_onay_ks.json"
TR = dt.timezone(dt.timedelta(hours=3))
HAT = {"masal_shorts": ("Masal", "17:00"), "ingilizce_shorts": ("İngilizce ders", "12:00")}


def _hat(ad):
    return "ingilizce_shorts" if ad.startswith("e") else "masal_shorts"


def _kayitlar():
    k = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    yuk, kaldi = {}, {}
    for x in k:
        ad = x["bolum"].rsplit("/", 1)[-1]
        if x.get("profil") != "shorts":
            continue
        if x.get("durum") == "yuklendi":
            yuk[ad] = x
        elif x.get("durum") == "kalite_kaldi":
            kaldi[ad] = kaldi.get(ad, 0) + 1
    return yuk, kaldi


def _ozet(ad, B, kayit, simdi):
    hat = _hat(ad)
    yt = (kayit or {}).get("youtube") or {}
    zaman = yt.get("publishAt") or (kayit or {}).get("tarih")
    gun, saat = "", HAT[hat][1]
    yayinda = False
    if zaman:
        z = dt.datetime.fromisoformat(zaman.replace("Z", "+00:00"))
        gun, saat = z.astimezone(TR).date().isoformat(), z.astimezone(TR).strftime("%H:%M")
        yayinda = z <= simdi
    vid = (kayit or {}).get("video_id")
    return {"id": ad[:-5], "gun": gun, "saat": saat, "baslik": B.get("baslik", ""), "bolum_no": B.get("bolum_no"), "hedef": HAT[hat][0],
            "sektor": hat, "konu": B.get("deger") or "",
            "durum": ("yayinlandi" if yayinda else "zamanlandi") if kayit else "sirada",
            "platformlar": [{"anahtar": "youtube", "ad": "YouTube Shorts", "durum": ("paylasildi" if yayinda else "zamanlandi") if kayit else "bekliyor",
                             "link": f"https://youtube.com/shorts/{vid}" if vid else None}],
            "satirlar": [{"id": f"{c.get('id')}.{i}", "kim": str(s.get("kim", "")).title(), "metin": s.get("metin", ""), "dil": s.get("dil")}
                         for c in B.get("cekimler", []) for i, s in enumerate(c.get("satirlar", []))],
            "duzenlenebilir": not kayit,
            "kilit_nedeni": "Video üretilip YouTube'a yüklendi; değişiklik Studio'dan yapılır." if kayit else None}


# Haftalık uzun videolar (derleme.py, haftalik-uzun.yml): pazar haftalık, çarşamba "Uyku Öncesi Masallar", cuma İngilizce — 10:07 TR
UZUN = {"haftalik": ("Haftalık derleme", 6), "karisik": ("Uyku Öncesi Masallar", 2), "ingilizce": ("İngilizce derleme", 4)}
UZUN_SAAT = "20:00"  # akış 10:07 TR başlar; çizim+derleme sürdüğü için yükleme genelde akşam


def _kapak_durumu(vid, kayit):
    kd = KOK / "kapaklar" / "durum.json"
    tamam = json.loads(kd.read_text()) if kd.exists() else {}
    if vid in tamam or str(kayit.get("kapak", "")).startswith("yuklendi"):
        return {"anahtar": "kapak", "ad": "Özel kapak", "durum": "paylasildi", "link": None}
    return {"anahtar": "kapak", "ad": "Kapak: telefon doğrulaması bekliyor", "durum": "hata", "link": None}


def uzun_ozeti(simdi=None, geri_gun=14, ileri_gun=7):
    """Uzun videolar: son iki haftada yüklenenler + önümüzdeki 7 günün planlı derlemeleri (düzenlenemez, yalnız takip)."""
    simdi = simdi or dt.datetime.now(dt.timezone.utc)
    k = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    out, yapilan = [], set()
    for x in k:
        if x.get("profil") != "derleme" or x.get("durum") != "yuklendi" or not x.get("video_id"):
            continue
        z = dt.datetime.fromisoformat(x["tarih"].replace("Z", "+00:00"))
        if z < simdi - dt.timedelta(days=geri_gun):
            continue
        tur = x.get("tur") or "haftalik"
        ad = UZUN.get(tur, (tur, None))[0]
        yerel = z.astimezone(TR)
        yapilan.add((tur, yerel.isocalendar()[:2]))
        basliklar = []
        for yol in x.get("parcalar", []):
            try:
                basliklar.append(json.loads((KOK / yol).read_text()).get("baslik", ""))
            except (OSError, ValueError):
                pass
        vid = x["video_id"]
        out.append({"id": f"uzun-{vid}", "gun": yerel.date().isoformat(), "saat": yerel.strftime("%H:%M"), "baslik": f"{ad} · {len(x.get('parcalar', []))} bölüm",
                    "bolum_no": None, "hedef": "Uzun video", "sektor": "uzun_video",
                    "konu": f"{round(x.get('sure', 0) / 60, 1)} dk · " + ", ".join(b for b in basliklar if b)[:170],
                    "durum": "yayinlandi" if (x.get("youtube") or {}).get("privacyStatus") == "public" else "uretildi",
                    "platformlar": [{"anahtar": "youtube_uzun", "ad": "YouTube video", "durum": "paylasildi", "link": f"https://www.youtube.com/watch?v={vid}"},
                                    _kapak_durumu(vid, x)],
                    "satirlar": [], "duzenlenebilir": False, "kilit_nedeni": "Uzun video Shorts bölümlerinden otomatik derlenir; bölümleri Masal sekmesinden düzenleyebilirsin."})
    bugun = simdi.astimezone(TR).date()
    for i in range(ileri_gun + 1):
        g = bugun + dt.timedelta(days=i)
        for tur, (ad, wd) in UZUN.items():
            if g.weekday() != wd or (tur, g.isocalendar()[:2]) in yapilan:
                continue
            out.append({"id": f"uzun-{tur}-{g.isoformat()}", "gun": g.isoformat(), "saat": UZUN_SAAT, "baslik": ad, "bolum_no": None,
                        "hedef": "Uzun video", "sektor": "uzun_video", "konu": "O hafta yayınlanan Shorts bölümlerinden otomatik derlenir; yükleme genelde akşam saatlerinde.",
                        "durum": "sirada", "platformlar": [{"anahtar": "youtube_uzun", "ad": "YouTube video", "durum": "bekliyor", "link": None}],
                        "satirlar": [], "duzenlenebilir": False, "kilit_nedeni": "Uzun video yayın günü otomatik derlenir."})
    return out


def takvim_ozeti(simdi=None, sirada=7):
    simdi = simdi or dt.datetime.now(dt.timezone.utc)
    yuk, kaldi = _kayitlar()
    adlar = sorted(p.name for p in SERI.glob("bolumler/[be]*.json"))
    sira_dosyasi = SERI / "yayin_sirasi.json"
    oncelik = [f"{a}.json" for a in (json.loads(sira_dosyasi.read_text()) if sira_dosyasi.exists() else []) if f"{a}.json" in adlar]
    secilen = []
    for ad, k in yuk.items():
        z = (k.get("youtube") or {}).get("publishAt") or k.get("tarih")
        if z and dt.datetime.fromisoformat(z.replace("Z", "+00:00")) >= simdi - dt.timedelta(days=7) and ad in adlar:
            secilen.append((ad, k))
    for hat in HAT:
        sira = [a for a in adlar if _hat(a) == hat]
        if hat == "masal_shorts":
            sira = [a for a in oncelik if _hat(a) == hat] + [a for a in sira if a not in oncelik]
        secilen += [(a, None) for a in [a for a in sira if a not in yuk and kaldi.get(a, 0) < 2][:sirada]]
    return [_ozet(ad, json.loads((SERI / "bolumler" / ad).read_text()), k, simdi) for ad, k in secilen] + uzun_ozeti(simdi)


def uygula(duzenlemeler):
    yuk, _ = _kayitlar()
    seri = json.loads((SERI / "seri.json").read_text())
    uyg, ret, ozgun = [], [], {}
    for d in duzenlemeler:
        bid = str(d.get("bolum_id", ""))
        yol = SERI / "bolumler" / f"{bid}.json"
        if not re.fullmatch(r"[be]\d{3}", bid) or not yol.exists():
            ret.append({"id": d["id"], "neden": "bölüm bulunamadı"}); continue
        if f"{bid}.json" in yuk:
            ret.append({"id": d["id"], "neden": "bölüm bu arada üretilip yüklendi"}); continue
        eski = yol.read_text()
        B = json.loads(eski)
        # uzunluk sınırı bu senkrondaki İLK hâle göre (art arda düzenlemeyle replik büyümesin; panel de asıl metne göre ölçer)
        ilk = ozgun.setdefault(bid, {f"{c.get('id')}.{i}": str(x.get("metin", "")) for c in B.get("cekimler", []) for i, x in enumerate(c.get("satirlar", []))})
        cek = {c.get("id"): c for c in B.get("cekimler", [])}
        hata = None
        for k, metin in (d.get("satirlar") or {}).items():
            cid, _, i = k.partition(".")
            try:
                s = cek[cid]["satirlar"][int(i)]
            except (KeyError, IndexError, ValueError):
                hata = f"bilinmeyen replik {k}"; break
            t = " ".join(str(metin).split())
            if not t or len(t.split()) > len(ilk.get(k, "").split()) + 4:
                hata = "replik boş ya da çok uzun"; break
            s["metin"] = t
        if not hata:
            h = bolum_denetle.denetle(B, seri)
            if h:
                hata = "bölüm denetimi: " + "; ".join(h[:3])
        if hata:
            ret.append({"id": d["id"], "neden": hata}); continue
        yol.write_text(json.dumps(B, ensure_ascii=False, indent=1) + "\n")
        uyg.append(d["id"])
        print(f"panel düzenlemesi uygulandı: {bid}", flush=True)
    return uyg, ret


def _gonderildi():
    try:
        subprocess.run(["git", "fetch", "-q", "origin"], cwd=KOK, timeout=60, check=True)
        return subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], cwd=KOK, timeout=30).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def fikirleri_yaz(tanitimlar, en_cok=2):
    """Paneldeki "İçerik fikri" → yeni masal bölümü (stok sırasına eklenir; depoya akıştaki adım yazar). Gemini yoksa fikir panelde bekler."""
    if not tanitimlar or not os.environ.get("GEMINI_API_KEY"):
        return []
    from otonom import masal_yaz
    out = []
    for t in tanitimlar[:en_cok]:
        no = max(int(p.stem[1:]) for p in SERI.glob("bolumler/b*.json")) + 1
        try:
            yol = masal_yaz.yaz_bir(no, istek=str(t.get("metin") or ""))
        except Exception as e:  # noqa: BLE001 — kota/ağ: fikir bekler, sonraki senkronda yeniden denenir
            print("içerik fikri yazılamadı (sonra denenecek):", str(e)[:200], flush=True)
            continue
        if yol:
            b = json.loads(yol.read_text())
            out.append({"id": t["id"], "durum": "planlandi", "gun": None, "aciklama": f"\"{b['baslik']}\" bölümü yazıldı ({b['deger']}); yayın sırasına eklendi"})
        else:
            out.append({"id": t["id"], "durum": "reddedildi", "neden": "Bu fikirden çocuk güvenliği ve dizi kurallarına uyan bölüm yazılamadı."})
    return out


def _belge():
    url, tok = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not tok:
        raise RuntimeError("OIDC yok (akışa 'permissions: id-token: write' gerekir)")
    r = requests.get(url, params={"audience": AUD}, headers={"Authorization": f"bearer {tok}"}, timeout=30)
    r.raise_for_status()
    return r.json()["value"]


def _kota_ekler():
    """Panel tablosundaki 'Yapay zekâ' rozeti (2026-11-27): otonom/kota.json (rakam/anahtar yok)."""
    try:
        import pathlib
        from ortak.kota_kaydi import rozet
        return {"baglanti": {"minik_masal": {"gemini": rozet(pathlib.Path(__file__).resolve().parent)}}}
    except Exception:  # noqa: BLE001
        return {}


def _post(yol, govde):
    r = requests.post(f"{PANEL}/api/icerik-takvimi/senkron/{KANAL}{yol}", json=govde, timeout=60,
                      headers={"Authorization": f"Bearer {_belge()}", "X-Requested-With": "ajans-web"})
    if not r.ok:
        raise RuntimeError(f"panel {r.status_code}: {r.text[:200]}")
    return r.json()


def duzelt_raporu():
    """Panel "Düzelt": YouTube yetkisini ve son videoların YouTube'daki durumunu OKUYARAK denetler (yükleme yapmaz).
    Yükleme hataları kendi akışında (gunluk3d) otomatik yeniden denenir; kapak için telefon doğrulaması insan adımıdır."""
    from otonom import saglik
    adimlar, eylemler = [], []
    h = saglik.token_dene("Minik Masal Evi", os.environ.get("YT_REFRESH_TOKEN"))
    if h:
        adimlar.append({"ad": "YouTube bağlantısı", "durum": "hata", "mesaj": "Yetki geçersiz ya da tanımlı değil"})
        eylemler.append({"ad": "YouTube kanal yetkisini kontrol et", "link": "https://myaccount.google.com/connections"})
    else:
        adimlar.append({"ad": "YouTube bağlantısı", "durum": "tamam", "mesaj": "Yetki geçerli"})
        try:
            sorun, _ = saglik.video_durumlari("Minik Masal Evi", "yayin_kaydi.json")
            adimlar.append({"ad": "Son videolar YouTube'da", "durum": "hata" if sorun else "tamam",
                            "mesaj": f"{len(sorun)} video reddedildi/işlenemedi" if sorun else "Reddedilen ya da işlenemeyen video yok"})
        except Exception as e:  # noqa: BLE001
            adimlar.append({"ad": "Son videolar YouTube'da", "durum": "uyari", "mesaj": f"okunamadı ({type(e).__name__})"})
    kayit = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    kapaksiz = [k for k in kayit[-10:] if k.get("video_id") and _kapak_durumu(k["video_id"], k)["durum"] == "hata"]
    if kapaksiz:
        adimlar.append({"ad": "Özel kapaklar", "durum": "uyari", "mesaj": f"{len(kapaksiz)} videoda özel kapak yüklenemedi: kanal telefonla doğrulanmalı"})
        eylemler.append({"ad": "YouTube kanalını telefonla doğrula", "link": "https://www.youtube.com/verify"})
    return {"durum": "sorun" if any(a["durum"] == "hata" for a in adimlar) else "tamam", "adimlar": adimlar, "eylemler": eylemler}


def main(komut):
    try:
        if komut == "al":
            cevap = _post("", {"bolumler": takvim_ozeti(), "ekler": _kota_ekler()})
            uyg, ret = uygula(cevap.get("duzenlemeler", []))
            fikir = fikirleri_yaz(cevap.get("tanitimlar", []))
            duzelt = []
            for c in cevap.get("komutlar", []):
                if c.get("tur") == "duzelt":
                    try:
                        duzelt.append({"id": c["id"], **duzelt_raporu()})
                    except Exception as e:  # noqa: BLE001
                        duzelt.append({"id": c["id"], "durum": "sorun", "adimlar": [{"ad": "Denetim yarıda kaldı", "durum": "hata", "mesaj": type(e).__name__}]})
                    uyg.append(c["id"])
            ONAY.write_text(json.dumps({"uygulanan": uyg, "reddedilen": ret, "tanitim": fikir, "duzelt": duzelt}))
            print(f"panel: takvim gönderildi; {len(uyg)} düzenleme uygulandı, {len(ret)} reddedildi, {len(fikir)} içerik fikri işlendi", flush=True)
        elif komut == "son":
            if ONAY.exists():
                o = json.loads(ONAY.read_text())
                yazildi = o["uygulanan"] or any(t["durum"] == "planlandi" for t in o.get("tanitim", []))
                if o.get("duzelt") and yazildi and not _gonderildi():  # düzelt raporu depo gönderiminden bağımsız gider
                    _post("/onay", {"uygulanan": [d["id"] for d in o["duzelt"]], "duzelt": o["duzelt"]})
                    o["uygulanan"] = [x for x in o["uygulanan"] if x not in {d["id"] for d in o["duzelt"]}]
                    o["duzelt"] = []
                if (o["uygulanan"] or o["reddedilen"] or o.get("tanitim") or o.get("duzelt")) and (not yazildi or _gonderildi()):
                    _post("/onay", o)
                ONAY.unlink()
            _post("", {"bolumler": takvim_ozeti(), "ekler": _kota_ekler()})
            print("panel: güncel takvim gönderildi", flush=True)
    except Exception as e:  # noqa: BLE001 — panel düşse de hat durmaz
        print("panel senkronu yapılamadı (hat etkilenmez):", str(e)[:300], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "al"))
