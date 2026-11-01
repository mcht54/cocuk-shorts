"""Günlük sağlık denetimi (saglik.yml): iki kanal gerçekten yayın yapıyor mu, stok ve yetkiler yerinde mi.

Sorun varsa çıkış 1 + sorun listesi (iş akışı GitHub issue açar -> sahibine e-posta). Ayrıca nabız dosyası
yazılır: depo her gün commit aldığı için GitHub, 60 gün hareketsiz depolarda zamanlanmış işleri kapatmaz.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from otonom import takvim

DEPO = Path(__file__).resolve().parent.parent
SIMDI = datetime.now(timezone.utc)
# (ad, kayıt dosyası, süzgeç, takvim hattı ya da en çok kaç saat sessiz kalabilir)
BEKLENEN = [
    ("Minik Masal Evi Shorts", "yayin_kaydi.json", lambda k: k.get("profil") == "shorts", "masal_shorts"),
    ("Minik Masal Evi haftalık uzun", "yayin_kaydi.json", lambda k: k.get("profil") == "derleme", 8 * 24 + 12),
    ("Merak Arşivi Shorts", "merak/kayit.json", lambda k: k.get("profil") == "shorts", "merak_shorts"),
    ("Merak Arşivi uzun belgesel", "merak/kayit.json", lambda k: k.get("profil") == "uzun", "merak_uzun"),
]
YAKIN = timedelta(hours=48)  # bu kadar içindeki yayın saatleri boşsa sorun (onay penceresi 7 gün)


def son_yukleme(dosya, suzgec):
    yol = DEPO / dosya
    kayit = json.loads(yol.read_text()) if yol.exists() else []
    tarihler = [datetime.fromisoformat(k["tarih"]) for k in kayit if suzgec(k) and k.get("durum") == "yuklendi"]
    return max(tarihler) if tarihler else None


ERISIM = {}  # ad -> erişim anahtarı (video durum denetimi için)


def token_dene(ad, refresh):
    if not refresh:
        return f"{ad}: yenileme anahtarı (secret) tanımlı değil"
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ.get("YT_CLIENT_ID"), "client_secret": os.environ.get("YT_CLIENT_SECRET"),
        "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=30)
    if not r.ok:
        return (f"{ad}: YouTube yetkisi geçersiz ({r.status_code} {r.text[:120]}). "
                "Yerelde `python yetki_al.py client_secret_findik.json` ile yenileyip secret'ı güncelleyin.")
    ERISIM[ad] = r.json().get("access_token")
    return None


def video_durumlari(ad, dosya, adet=20):
    """Son yüklenen videoların YouTube'daki durumu: (sorunlar, rapor satırı). Silinen video sorun sayılmaz
    (haftalık onayda silmek serbest); YouTube'un reddettiği / işleyemediği video sorundur."""
    yol = DEPO / dosya
    kayit = [k for k in (json.loads(yol.read_text()) if yol.exists() else [])
             if k.get("durum") == "yuklendi" and k.get("video_id")][-adet:]
    if not kayit or not ERISIM.get(ad):
        return [], None
    r = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=30,
                     headers={"Authorization": f"Bearer {ERISIM[ad]}"},
                     params={"part": "status", "id": ",".join(k["video_id"] for k in kayit), "maxResults": 50})
    if not r.ok:
        return [f"{ad}: video durumu okunamadı ({r.status_code} {r.text[:120]})"], None
    durum = {v["id"]: v["status"] for v in r.json().get("items", [])}
    sorunlar, silinen = [], []
    for k in kayit:
        st = durum.get(k["video_id"])
        if st is None:
            silinen.append(k["video_id"])
        elif st.get("uploadStatus") in ("rejected", "failed"):
            neden = st.get("rejectionReason") or st.get("failureReason") or "?"
            sorunlar.append(f"{ad}: video {k['video_id']} YouTube tarafından {st['uploadStatus']} ({neden}) - "
                            f"{k.get('bolum', '')}")
    satir = (f"- {ad} YouTube: son {len(kayit)} videodan {len(kayit) - len(silinen)} yerinde"
             + (f", silinmiş: {', '.join(silinen)}" if silinen else ""))
    return sorunlar, satir


def main():
    sorunlar, rapor = [], []
    acik = os.environ.get("YAYIN") == "acik"
    baslangic = {"Merak Arşivi": os.environ.get("MERAK_BASLANGIC", ""),
                 "Minik Masal Evi haftalık": os.environ.get("DERLEME_BASLANGIC", "")}
    for ad, dosya, suzgec, olcut in BEKLENEN:
        son = son_yukleme(dosya, suzgec)
        rapor.append(f"- {ad}: son yükleme {son:%Y-%m-%d %H:%M} UTC" if son else f"- {ad}: henüz yükleme yok")
        # henüz başlamamış hat (başlangıç tarihi gelmemiş/girilmemiş) sorun sayılmaz
        bas = next((v for k, v in baslangic.items() if ad.startswith(k)), None)
        if bas is not None and (not bas or SIMDI < datetime.fromisoformat(bas)):
            continue
        if not acik:
            continue
        if isinstance(olcut, str):  # takvimli hat: yakın saatler zamanlanmış olmalı
            yol = DEPO / dosya
            kayit = [k for k in (json.loads(yol.read_text()) if yol.exists() else []) if suzgec(k)]
            bos = [s for s in takvim.bos_slotlar(olcut, kayit, SIMDI) if s <= SIMDI + YAKIN]
            if bos:
                sorunlar.append(f"{ad}: {len(bos)} yakın yayın saati boş (ilki {bos[0]:%Y-%m-%d %H:%M} UTC). "
                                "Actions sekmesindeki son çalıştırmanın günlüğüne bakın.")
        elif not son or SIMDI - son > timedelta(hours=olcut):
            sorunlar.append(f"{ad}: {olcut} saattir yükleme yok (son: {son or 'hiç'}).")
    for ad, anahtar in (("Minik Masal Evi", "YT_REFRESH_TOKEN"), ("Merak Arşivi", "MERAK_YT_REFRESH_TOKEN")):
        if ad == "Merak Arşivi" and not os.environ.get("MERAK_BASLANGIC"):
            continue
        h = token_dene(ad, os.environ.get(anahtar))
        if h:
            sorunlar.append(h)
            continue
        try:
            s, satir = video_durumlari(ad, "yayin_kaydi.json" if ad == "Minik Masal Evi" else "merak/kayit.json")
            sorunlar += s
            if satir:
                rapor.append(satir)
        except requests.RequestException as e:
            rapor.append(f"- {ad} YouTube: video durumu okunamadı ({e})")
    if not os.environ.get("GEMINI_API_KEY"):
        sorunlar.append("GEMINI_API_KEY secret'ı yok: yeni bölüm/konu yazılamıyor, stok tükenince yayın durur.")
    try:
        from otonom import stok
        from merak import yayinla
        m = stok.masal_stogu()
        u, k = len(yayinla.sira("uzun")), len(yayinla.sira("shorts"))
        rapor.append(f"- stok: masal {m} bölüm, merak {u} uzun / {k} Shorts")
        if m < stok.KRITIK_GUN:
            sorunlar.append(f"Minik Masal Evi stoku {m} bölüm (stok.yml çalışıyor mu? Gemini kotası?)")
        if os.environ.get("MERAK_BASLANGIC") and k < stok.KRITIK_GUN:
            sorunlar.append(f"Merak Arşivi Shorts stoku {k}")
    except Exception as e:
        sorunlar.append(f"stok okunamadı: {e}")
    (DEPO / "otonom" / "nabiz.json").write_text(json.dumps(
        {"tarih": SIMDI.isoformat(timespec="seconds"), "sorun_sayisi": len(sorunlar)}, ensure_ascii=False))
    metin = "## Sağlık raporu\n" + "\n".join(rapor) + "\n\n" + (
        "### Sorunlar\n" + "\n".join(f"- {s}" for s in sorunlar) if sorunlar else "Sorun yok.")
    print(metin)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(metin)
    Path(os.environ.get("RUNNER_TEMP", "/tmp")).joinpath("saglik.md").write_text(metin)
    return 1 if sorunlar else 0


if __name__ == "__main__":
    sys.exit(main())
