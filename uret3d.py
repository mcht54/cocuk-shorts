"""3D bölüm üretimi (yerel, Blender): plan -> sahne -> render (çekim çekim, kaldığı yerden)
-> kurgu -> kalite kontrolü -> rapor. Hiçbir şey yayımlamaz.

Kullanım:
  ./venv/bin/python uret3d.py --bolum seri/findik-ile-pamuk/bolumler/b001.json --profil shorts
  [--onizleme]   (yarı çözünürlük, düşük örnekleme: hızlı deneme)
  [--prototip]   (uzun profilde kısa prototip bölüme izin ver; raporda işaretlenir)
Çıktı: cikti3d/<seri>/<bolum>-<profil>[-onizleme].mp4 + .rapor.json

Bulutta parçalı üretim (24 fps / 1080p tek makinede 6 saati aşar; ciz.yml):
  --asama hazirla                      plan + sahne (uretim/<seri>/<ad> klasörü sonraki işlere taşınır)
  --asama ciz --parca i --parca-sayisi N   karelerin i. dilimini çizer
  --asama bitir                        tüm kareler hazırsa kurgu + kalite kontrolü + rapor
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from cocuk3d import kalite3d, kurgu, planla

KOK = Path(__file__).resolve().parent
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
BETIK = KOK / "cocuk3d" / "blender_sahne.py"
EN_AZ_BOS_DISK_GB = float(os.environ.get("EN_AZ_BOS_DISK_GB", 15))
RENDER_IS_PARCACIGI = int(os.environ.get("RENDER_IS_PARCACIGI", 8))  # 12 çekirdekten 8'i


def log(*p):
    print(f"[{datetime.now():%H:%M:%S}]", *p, flush=True)


def blender(*arg, zaman_asimi):
    komut = ["nice", "-n", "10", BLENDER, "-b", "--factory-startup", "-t", str(RENDER_IS_PARCACIGI),
             "-P", str(BETIK), "--", *map(str, arg)]
    r = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi)
    if r.returncode != 0 or "Traceback" in r.stdout + r.stderr:
        hata = (r.stdout + r.stderr)[-1500:]
        raise RuntimeError(f"Blender hatası ({arg[0]}):\n{hata}")
    return r.stdout


def ozet(yollar):
    h = hashlib.sha1()
    for y in yollar:
        h.update(Path(y).read_bytes())
    return h.hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bolum", required=True)
    ap.add_argument("--profil", choices=["shorts", "uzun"], required=True)
    ap.add_argument("--onizleme", action="store_true")
    ap.add_argument("--prototip", action="store_true")
    ap.add_argument("--ornekleme", type=int)
    ap.add_argument("--olcek", type=int, help="çözünürlük yüzdesi (bulut: 67 = 720p)")
    ap.add_argument("--seri", help="seri klasörü (varsayılan: bölüm dosyasının iki üstü)")
    ap.add_argument("--asama", choices=["tam", "hazirla", "ciz", "bitir"], default="tam")
    ap.add_argument("--parca", type=int, default=0)
    ap.add_argument("--parca-sayisi", type=int, default=1)
    a = ap.parse_args()

    bolum_yolu = Path(a.bolum).resolve()
    seri_dizini = Path(a.seri).resolve() if a.seri else bolum_yolu.parent.parent
    bolum = json.loads(bolum_yolu.read_text())
    ad = f"{bolum_yolu.stem}-{a.profil}" + ("-onizleme" if a.onizleme else "")  # b001 masal, e001 İngilizce
    is_dizini = KOK / "uretim" / bolum["seri_id"] / ad
    cikti_dizini = KOK / "cikti3d" / bolum["seri_id"]
    is_dizini.mkdir(parents=True, exist_ok=True)
    cikti_dizini.mkdir(parents=True, exist_ok=True)
    olcek = a.olcek or (50 if a.onizleme else 100)
    ornekleme = a.ornekleme or (8 if a.onizleme else 32)

    bos = shutil.disk_usage(KOK).free / 1e9
    if bos < EN_AZ_BOS_DISK_GB:
        raise SystemExit(f"Disk yetersiz: {bos:.0f} GB boş, en az {EN_AZ_BOS_DISK_GB:.0f} GB gerekli")
    log(f"{ad}: boş disk {bos:.0f} GB, ölçek %{olcek}, örnekleme {ornekleme}")

    durum_yolu = is_dizini / "durum.json"
    durum = json.loads(durum_yolu.read_text()) if durum_yolu.exists() else {}
    # yalnız görüntüyü/sesi etkileyen dosyalar (kurgu/kalite değişince render tekrarlanmaz)
    goruntu_kodu = [KOK / "cocuk3d" / f"{m}.py" for m in ("animasyon", "kamera", "planla", "ses3d",
                                                          "blender_sahne", "profil")]
    kaynak = ozet([bolum_yolu, seri_dizini / "seri.json", *goruntu_kodu])
    imza = f"{kaynak}-{olcek}-{ornekleme}-{a.prototip}-{os.environ.get('FPS', '')}"
    # ciz/bitir aşamaları hazirla işinin taşıdığı klasöre güvenir (aynı commit, aynı ayar)
    if a.asama in ("tam", "hazirla") and durum.get("imza") != imza:  # bölüm/kod/ayar değişti: baştan
        log("yeni ya da değişmiş iş: plan ve sahne yeniden kurulacak")
        for alt in ("kareler",):
            shutil.rmtree(is_dizini / alt, ignore_errors=True)
        for dosya in ("sahne.blend", "meta.json", "plan.json"):
            (is_dizini / dosya).unlink(missing_ok=True)
        durum = {"imza": imza}

    t0 = time.time()
    if not (is_dizini / "plan.json").exists():
        log("planlama (seslendirme dahil)...")
        planla.planla(seri_dizini, bolum_yolu, a.profil, is_dizini, prototip=a.prototip)
    plan = json.loads((is_dizini / "plan.json").read_text())
    if not (is_dizini / "sahne.blend").exists() or not (is_dizini / "meta.json").exists():
        log("Blender sahnesi kuruluyor...")
        cikti = blender("kur", is_dizini / "plan.json", is_dizini, ornekleme, olcek, zaman_asimi=900)
        log([s for s in cikti.splitlines() if "KURULUM_TAMAM" in s][0])
    durum_yolu.write_text(json.dumps(durum))
    if a.asama == "hazirla":
        log(f"hazır: {plan['kare_say']} kare, klasör {is_dizini.relative_to(KOK)}")
        return

    # çekim çekim render; yarım kalan (0 bayt yer tutucu) kareleri temizle
    kareler = is_dizini / "kareler"
    kareler.mkdir(exist_ok=True)
    for k in kareler.glob("k_*.png"):
        if k.stat().st_size == 0:
            k.unlink()
    if a.asama == "ciz":
        dilim = -(-plan["kare_say"] // a.parca_sayisi)
        b, s = a.parca * dilim, min(plan["kare_say"], (a.parca + 1) * dilim) - 1
        if b > s:
            log("bu parçaya kare düşmedi")
            return
        for deneme in range(1, 3):
            ts = time.time()
            try:
                blender("render", is_dizini, b, s,
                        zaman_asimi=max(900, int(os.environ.get("RENDER_SN_KARE", 12)) * (s - b + 1)))
                break
            except Exception as e:
                log(f"parça {a.parca}: render hatası (deneme {deneme}): {str(e)[-300:]}")
                for k in kareler.glob("k_*.png"):
                    if k.stat().st_size == 0:
                        k.unlink()
                if deneme == 2:
                    raise
        eksik = [f for f in range(b, s + 1) if not (kareler / f"k_{f:04d}.png").exists()]
        if eksik:
            raise SystemExit(f"parça {a.parca}: {len(eksik)} kare çizilemedi")
        log(f"parça {a.parca}/{a.parca_sayisi}: kare {b}-{s}, {time.time() - ts:.0f} sn "
            f"({(time.time() - ts) / (s - b + 1):.2f} sn/kare)")
        # yalnız bu parçanın kareleri taşınır
        for k in kareler.glob("k_*.png"):
            if not b <= int(k.stem[2:]) <= s:
                k.unlink()
        return
    if a.asama == "bitir":
        eksik = [f for f in range(plan["kare_say"]) if not (kareler / f"k_{f:04d}.png").exists()]
        if eksik:
            raise SystemExit(f"{len(eksik)} kare eksik (ilk {eksik[:5]}); parça işlerinden biri başarısız")
    for c in plan["cekimler"]:
        b, s = c["bas_kare"], c["bas_kare"] + c["kare_say"] - 1
        eksik = [f for f in range(b, s + 1) if not (kareler / f"k_{f:04d}.png").exists()]
        if not eksik:
            continue
        for deneme in range(1, 3):
            ts = time.time()
            try:
                blender("render", is_dizini, b, s,
                        zaman_asimi=max(900, int(os.environ.get("RENDER_SN_KARE", 12)) * c["kare_say"]))
                break
            except Exception as e:
                log(f"{c['id']}: render hatası (deneme {deneme}): {str(e)[-300:]}")
                for k in kareler.glob("k_*.png"):
                    if k.stat().st_size == 0:
                        k.unlink()
                if deneme == 2:
                    raise
        log(f"{c['id']}: {c['kare_say']} kare, {time.time() - ts:.0f} sn "
            f"({(time.time() - ts) / c['kare_say']:.2f} sn/kare)")

    zaman = datetime.now().strftime("%Y%m%d-%H%M")
    mp4 = cikti_dizini / f"{ad}-{zaman}.mp4"
    log("kurgu (altyazı + ses)...")
    alt = kurgu.birlestir(is_dizini, mp4)
    (is_dizini / "altyazi.json").write_text(json.dumps(alt))
    # videoyu değerlendiren veriler videonun yanında saklanır: sonraki render iş klasörünü
    # değiştirse bile bu video daima KENDİ ölçümüyle yeniden denetlenebilir
    veri = mp4.with_suffix(".veri")
    veri.mkdir()
    for dosya in ("meta.json", "kurgu.json", "altyazi.json"):
        shutil.copy2(is_dizini / dosya, veri / dosya)
    (veri / "video.sha256").write_text(hashlib.sha256(mp4.read_bytes()).hexdigest())

    log("kalite kontrolü...")
    tamam, hatalar, olcum = kalite3d.denetle(mp4, veri, seri_dizini)
    rapor = {"bolum": str(bolum_yolu.relative_to(KOK)), "profil": a.profil, "onizleme": a.onizleme,
             "prototip": a.prototip, "video": str(mp4.relative_to(KOK)), "kalite_gecti": tamam,
             "veri": str(veri.relative_to(KOK)),
             "hatalar": hatalar, "olcum": olcum, "uretim_suresi_sn": round(time.time() - t0),
             "yayin": "yok (yalnız yerel üretim)"}
    mp4.with_suffix(".rapor.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=1))
    log("KALİTE:", "GEÇTİ" if tamam else "KALDI")
    for h in hatalar:
        log("  -", h)

    if tamam:
        kayit = seri_dizini / "karakter_izleri.json"
        izler = json.loads(kayit.read_text()) if kayit.exists() else {}
        yeni = {k: v for k, v in olcum["parmak_izi"].items() if k not in izler}
        if yeni:
            izler.update(yeni)
            kayit.write_text(json.dumps(izler, indent=1))
            log("seriye karakter parmak izi kaydedildi:", yeni)
        shutil.rmtree(kareler, ignore_errors=True)  # geçen işin ara kareleri silinir; MP4 + rapor kalır
    else:
        log("kareler incelenmek üzere bırakıldı:", kareler)
    log("video:", mp4)
    sys.exit(0 if tamam else 1)


if __name__ == "__main__":
    main()
