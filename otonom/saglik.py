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

DEPO = Path(__file__).resolve().parent.parent
SIMDI = datetime.now(timezone.utc)
# (ad, kayıt dosyası, süzgeç, en çok kaç saat sessiz kalabilir)
BEKLENEN = [
    ("Minik Masal Evi Shorts", "yayin_kaydi.json", lambda k: k.get("profil") == "shorts", 50),
    ("Minik Masal Evi haftalık uzun", "yayin_kaydi.json", lambda k: k.get("profil") == "derleme", 8 * 24 + 12),
    ("Merak Arşivi Shorts", "merak/kayit.json", lambda k: k.get("profil") == "shorts", 50),
    ("Merak Arşivi uzun belgesel", "merak/kayit.json", lambda k: k.get("profil") == "uzun", 5 * 24),
]


def son_yukleme(dosya, suzgec):
    yol = DEPO / dosya
    kayit = json.loads(yol.read_text()) if yol.exists() else []
    tarihler = [datetime.fromisoformat(k["tarih"]) for k in kayit if suzgec(k) and k.get("durum") == "yuklendi"]
    return max(tarihler) if tarihler else None


def token_dene(ad, refresh):
    if not refresh:
        return f"{ad}: yenileme anahtarı (secret) tanımlı değil"
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ.get("YT_CLIENT_ID"), "client_secret": os.environ.get("YT_CLIENT_SECRET"),
        "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=30)
    if not r.ok:
        return (f"{ad}: YouTube yetkisi geçersiz ({r.status_code} {r.text[:120]}). "
                "Yerelde `python yetki_al.py client_secret_findik.json` ile yenileyip secret'ı güncelleyin.")
    return None


def main():
    sorunlar, rapor = [], []
    acik = os.environ.get("YAYIN") == "acik"
    baslangic = {"Merak Arşivi": os.environ.get("MERAK_BASLANGIC", ""),
                 "Minik Masal Evi haftalık": os.environ.get("DERLEME_BASLANGIC", "")}
    for ad, dosya, suzgec, saat in BEKLENEN:
        son = son_yukleme(dosya, suzgec)
        rapor.append(f"- {ad}: son yükleme {son:%Y-%m-%d %H:%M} UTC" if son else f"- {ad}: henüz yükleme yok")
        # henüz başlamamış hat (başlangıç tarihi gelmemiş/girilmemiş) sorun sayılmaz
        bas = next((v for k, v in baslangic.items() if ad.startswith(k)), None)
        if bas is not None and (not bas or SIMDI < datetime.fromisoformat(bas) + timedelta(hours=saat)):
            continue
        if acik and (not son or SIMDI - son > timedelta(hours=saat)):
            sorunlar.append(f"{ad}: {saat} saattir yükleme yok (son: {son or 'hiç'}). Actions sekmesindeki son "
                            "çalıştırmanın günlüğüne bakın.")
    for ad, anahtar in (("Minik Masal Evi", "YT_REFRESH_TOKEN"), ("Merak Arşivi", "MERAK_YT_REFRESH_TOKEN")):
        if ad == "Merak Arşivi" and not os.environ.get("MERAK_BASLANGIC"):
            continue
        h = token_dene(ad, os.environ.get(anahtar))
        if h:
            sorunlar.append(h)
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
