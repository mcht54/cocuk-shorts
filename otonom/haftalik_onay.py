"""Haftalık onay listesi: önümüzdeki 7 günde yayınlanacak (zamanlanmış) videolar.

haftalik-onay.yml bunu "Haftalık onay" issue'su olarak açar; GitHub sahibine e-posta gönderir.
Kullanıcı beğenmediği videoyu YouTube Studio'da siler ya da gizliye alır; dokunulmayan saatinde yayınlanır.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEPO = Path(__file__).resolve().parent.parent
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
KANALLAR = [("Minik Masal Evi", DEPO / "yayin_kaydi.json"), ("Merak Arşivi", DEPO / "merak" / "kayit.json")]


def baslik(k):
    if k.get("konu"):
        yol = DEPO / "merak" / "konular" / k["konu"] / f"{k['senaryo']}.json"
    else:
        yol = DEPO / k.get("bolum", "")
    try:
        v = json.loads(yol.read_text())
        return (v.get("youtube") or {}).get("baslik") or v.get("baslik") or yol.stem
    except (OSError, ValueError):
        return k.get("bolum") or k.get("senaryo") or "?"


def liste(simdi=None):
    simdi = simdi or datetime.now(timezone.utc)
    satir = ["Önümüzdeki 7 günde yayınlanacak videolar. **Beğenmediğiniz videoyu YouTube Studio'da açıp "
             "silin ya da Görünürlük → Gizli yapın.** Hiçbir şey yapmazsanız saatinde yayınlanır.", ""]
    toplam = 0
    for kanal, yol in KANALLAR:
        kayit = json.loads(yol.read_text()) if yol.exists() else []
        gelecek = sorted((k for k in kayit if k.get("durum") == "yuklendi" and k.get("yayin_zamani")
                          and simdi < datetime.fromisoformat(k["yayin_zamani"]) <= simdi + timedelta(days=7)),
                         key=lambda k: k["yayin_zamani"])
        satir.append(f"### {kanal} ({len(gelecek)} video)")
        for k in gelecek:
            z = datetime.fromisoformat(k["yayin_zamani"]) + timedelta(hours=3)  # Türkiye saati
            tur = "Shorts" if k.get("profil") == "shorts" else "Uzun"
            satir.append(f"- {GUNLER[z.weekday()]} {z:%d.%m %H:%M} · {tur} · {baslik(k)} — "
                         f"[izle](https://youtube.com/watch?v={k['video_id']}) · "
                         f"[Studio'da düzenle](https://studio.youtube.com/video/{k['video_id']}/edit)")
        if not gelecek:
            satir.append("- (zamanlanmış video yok)")
        satir.append("")
        toplam += len(gelecek)
    return "\n".join(satir), toplam


if __name__ == "__main__":
    metin, n = liste()
    Path(os.environ.get("RUNNER_TEMP", "/tmp"), "onay.md").write_text(metin)
    print(metin)
