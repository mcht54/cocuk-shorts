"""Yerel üretim kuyruğu (yayın YAPMAZ). Durum: uretim/kuyruk.json

  ./venv/bin/python kuyruk.py ekle <bolum.json> shorts|uzun [--prototip]
  ./venv/bin/python kuyruk.py liste
  ./venv/bin/python kuyruk.py calistir [--toplu N]      # sıradaki iş(ler)
  ./venv/bin/python kuyruk.py plan-dosyasi gunluk|haftalik  # launchd dosyası üretir, YÜKLEMEZ

Kurallar: aynı bölüm+profil kuyrukta iki kez olmaz; bir iş en fazla 2 kez denenir;
günlük iş ve render süresi sınırı; disk sınırı uret3d.py'de; önce önizleme geçmeli.
Bu kuyruk yalnız bilgisayar açık ve uyanıkken çalışır.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent
DOSYA = Path(os.environ.get("KUYRUK_DOSYASI", KOK / "uretim" / "kuyruk.json"))
GUNLUK_IS = int(os.environ.get("GUNLUK_IS_SINIRI", 4))
GUNLUK_DAKIKA = int(os.environ.get("GUNLUK_RENDER_DAKIKA", 120))
EN_FAZLA_DENEME = 2


def oku():
    return json.loads(DOSYA.read_text()) if DOSYA.exists() else {"isler": []}


def yaz(k):
    DOSYA.parent.mkdir(parents=True, exist_ok=True)
    gecici = DOSYA.with_suffix(".tmp")
    gecici.write_text(json.dumps(k, ensure_ascii=False, indent=1))
    gecici.replace(DOSYA)  # yarım yazılmış kuyruk dosyası olmasın


def ekle(k, bolum, profil, prototip):
    bolum = str(Path(bolum).resolve().relative_to(KOK))
    for i in k["isler"]:
        if i["bolum"] == bolum and i["profil"] == profil and i["durum"] != "hata":
            return None  # çift iş yok
    is_ = {"id": f"{Path(bolum).stem}-{profil}-{int(time.time())}", "bolum": bolum, "profil": profil,
           "prototip": prototip, "durum": "bekliyor", "asama": "onizleme", "deneme": 0,
           "eklendi": datetime.now().isoformat(timespec="seconds"), "gecmis": []}
    k["isler"].append(is_)
    return is_


def bugun(k):
    g = datetime.now().date().isoformat()
    calisan = [h for i in k["isler"] for h in i["gecmis"] if h["bas"][:10] == g]
    return len(calisan), sum(h.get("sure_sn", 0) for h in calisan) / 60


def sonraki(k):
    for i in k["isler"]:
        if i["durum"] in ("bekliyor", "yeniden_dene"):
            return i
    return None


def calistir_bir(k, komut_ureteci=None):
    i = sonraki(k)
    if not i:
        return None
    say, dakika = bugun(k)
    if say >= GUNLUK_IS or dakika >= GUNLUK_DAKIKA:
        print(f"günlük sınır doldu ({say} iş, {dakika:.0f} dk); yarın devam")
        return None
    komut = [sys.executable, str(KOK / "uret3d.py"), "--bolum", i["bolum"], "--profil", i["profil"]]
    if i["prototip"]:
        komut.append("--prototip")
    if i["asama"] == "onizleme":
        komut.append("--onizleme")
    komut = (komut_ureteci or (lambda c: c))(komut)
    i["durum"], i["deneme"] = "calisiyor", i["deneme"] + 1
    yaz(k)
    bas = datetime.now()
    r = subprocess.run(komut, capture_output=True, text=True)
    sure = (datetime.now() - bas).total_seconds()
    satirlar = (r.stdout + r.stderr).strip().splitlines()
    video = next((s.split("video: ", 1)[1] for s in satirlar if "video: " in s), None)
    i["gecmis"].append({"bas": bas.isoformat(timespec="seconds"), "asama": i["asama"], "kod": r.returncode,
                        "sure_sn": round(sure), "video": video, "son": satirlar[-8:]})
    if r.returncode == 0 and i["asama"] == "onizleme":
        i["asama"], i["durum"], i["deneme"] = "tam", "bekliyor", 0  # önizleme geçti -> tam kalite
    elif r.returncode == 0:
        i["durum"], i["video"] = "gecti", video
    elif i["deneme"] < EN_FAZLA_DENEME:
        i["durum"] = "yeniden_dene"
    else:
        i["durum"] = "hata"
        i["son_hata"] = satirlar[-8:]
    yaz(k)
    return i


PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>tr.mchttasarim.cocuk3d</string>
  <key>ProgramArguments</key><array>
    <string>{py}</string><string>{kuyruk}</string><string>calistir</string><string>--toplu</string><string>2</string>
  </array>
  <key>WorkingDirectory</key><string>{kok}</string>
  <key>StartCalendarInterval</key>{zaman}
  <key>StandardOutPath</key><string>{kok}/uretim/zamanlayici.log</string>
  <key>StandardErrorPath</key><string>{kok}/uretim/zamanlayici.log</string>
  <key>LowPriorityIO</key><true/><key>Nice</key><integer>10</integer>
</dict></plist>
"""


def main():
    ap = argparse.ArgumentParser()
    alt = ap.add_subparsers(dest="komut", required=True)
    e = alt.add_parser("ekle")
    e.add_argument("bolum")
    e.add_argument("profil", choices=["shorts", "uzun"])
    e.add_argument("--prototip", action="store_true")
    alt.add_parser("liste")
    c = alt.add_parser("calistir")
    c.add_argument("--toplu", type=int, default=1)
    p = alt.add_parser("plan-dosyasi")
    p.add_argument("siklik", choices=["gunluk", "haftalik"])
    a = ap.parse_args()

    k = oku()
    if a.komut == "ekle":
        is_ = ekle(k, a.bolum, a.profil, a.prototip)
        yaz(k)
        print("eklendi:" if is_ else "zaten kuyrukta:", is_["id"] if is_ else a.bolum)
    elif a.komut == "liste":
        for i in k["isler"]:
            print(f"{i['id']:40s} {i['durum']:13s} aşama={i['asama']:9s} deneme={i['deneme']} {i.get('video') or ''}")
        say, dk = bugun(k)
        print(f"bugün: {say}/{GUNLUK_IS} iş, {dk:.0f}/{GUNLUK_DAKIKA} dk render")
    elif a.komut == "calistir":
        for _ in range(a.toplu):
            i = calistir_bir(k)
            if not i:
                break
            print(i["id"], "->", i["durum"], i["asama"])
    elif a.komut == "plan-dosyasi":
        zaman = ("<dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>"
                 if a.siklik == "gunluk" else
                 "<dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>3</integer>"
                 "<key>Minute</key><integer>0</integer></dict>")
        hedef = KOK / "uretim" / "tr.mchttasarim.cocuk3d.plist"
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(PLIST.format(py=sys.executable, kuyruk=KOK / "kuyruk.py", kok=KOK, zaman=zaman))
        print(f"oluşturuldu (YÜKLENMEDİ): {hedef}\n"
              "Etkinleştirmek ayrı onay ister: cp <dosya> ~/Library/LaunchAgents/ && "
              "launchctl load ~/Library/LaunchAgents/tr.mchttasarim.cocuk3d.plist\n"
              "Not: Mac kapalı/uykudayken çalışmaz; uyanınca kaçırılan çalıştırmayı bir kez yapar.")


if __name__ == "__main__":
    main()
