"""Yayın öncesi kalite kontrolü: gerçek MP4 dosyası ffprobe/ffmpeg ile denetlenir.

Bozuk, sessiz, eksik görüntülü, yanlış süreli ya da altyazısı eksik video
yayımlanmaz. denetle() -> (tamam, hatalar, olcumler).
"""
import json
import re
import subprocess

from PIL import Image, ImageChops, ImageStat

from .gorsel import gorsel_kontrol

G, Y = 1080, 1920
EN_KISA, EN_UZUN = 15.0, 59.0  # Shorts için güvenli aralık (sn)


def _ffprobe(yol):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                        "-show_format", "-show_streams", str(yol)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffprobe dosyayı okuyamadı: " + r.stderr[:200])
    return json.loads(r.stdout)


def _ses_analizi(yol):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(yol), "-vn",
                        "-af", "silencedetect=noise=-45dB:d=2.0,volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    cikti = r.stderr
    ort = re.search(r"mean_volume: (-?[\d.]+) dB", cikti)
    tepe = re.search(r"max_volume: (-?[\d.]+) dB", cikti)
    sessizlik = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", cikti)]
    return {"ortalama_db": float(ort.group(1)) if ort else None,
            "tepe_db": float(tepe.group(1)) if tepe else None,
            "uzun_sessizlik_sn": sessizlik}


def _kare(yol, saniye):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{saniye:.2f}", "-i", str(yol),
                        "-frames:v", "1", "-vf", "scale=270:480", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True)
    if r.returncode != 0 or len(r.stdout) != 270 * 480 * 3:
        return None
    return Image.frombytes("RGB", (270, 480), r.stdout)


def denetle(yol, rapor):
    """rapor: video.uret() çıktısı (beklenen süre, sahne başları, altyazı ölçümü)."""
    hatalar, olcum = [], {}
    try:
        bilgi = _ffprobe(yol)
    except Exception as e:
        return False, [str(e)], olcum

    v = [s for s in bilgi["streams"] if s["codec_type"] == "video"]
    a = [s for s in bilgi["streams"] if s["codec_type"] == "audio"]
    sure = float(bilgi["format"].get("duration", 0))
    olcum.update({"dosya_sure": round(sure, 2), "beklenen_sure": rapor["sure"],
                  "boyut_mb": round(int(bilgi["format"].get("size", 0)) / 1e6, 2)})
    if not v:
        hatalar.append("video akışı yok")
    elif (int(v[0]["width"]), int(v[0]["height"])) != (G, Y):
        hatalar.append(f"çözünürlük {v[0]['width']}x{v[0]['height']} (beklenen {G}x{Y})")
    if not a:
        hatalar.append("ses akışı yok")
    else:
        olcum["ses_sure"] = round(float(a[0].get("duration", sure)), 2)
    if v:
        olcum["goruntu_sure"] = round(float(v[0].get("duration", sure)), 2)
    if abs(sure - rapor["sure"]) > 0.35:
        hatalar.append(f"süre uyuşmuyor: dosya {sure:.2f} sn, beklenen {rapor['sure']:.2f} sn")
    if not EN_KISA <= sure <= EN_UZUN:
        hatalar.append(f"süre {sure:.1f} sn; izin verilen {EN_KISA:.0f}-{EN_UZUN:.0f} sn")
    if a and v and abs(olcum["ses_sure"] - olcum["goruntu_sure"]) > 0.3:
        hatalar.append(f"ses ({olcum['ses_sure']}) ve görüntü ({olcum['goruntu_sure']}) süreleri farklı")

    # ses / müzik / konuşma
    if rapor["ses_ornek"] != rapor["muzik_ornek"]:
        hatalar.append("müzik ve konuşma izleri farklı uzunlukta")
    if rapor["konusma_son"] > sure:
        hatalar.append("konuşma video bitmeden kesiliyor")
    ses = _ses_analizi(yol)
    olcum["ses"] = ses
    if ses["ortalama_db"] is None or ses["ortalama_db"] < -35:
        hatalar.append(f"ses çok kısık ya da yok (ortalama {ses['ortalama_db']} dB)")
    if ses["tepe_db"] is not None and ses["tepe_db"] > -0.1:
        hatalar.append("ses kırpılıyor (tepe 0 dB)")
    if ses["uzun_sessizlik_sn"]:
        hatalar.append(f"2 sn'den uzun sessizlik var: {ses['uzun_sessizlik_sn']}")

    # altyazı
    alt = rapor["altyazi"]
    olcum["altyazi"] = alt
    if alt["gosterilmeyen"] > 0:
        hatalar.append(f"{alt['gosterilmeyen']} kelime söylenirken altyazıda görünmedi")
    if alt["en_uzun_bosluk_sn"] > 0.8:
        hatalar.append(f"konuşma sırasında {alt['en_uzun_bosluk_sn']} sn altyazısız kalıyor")

    # görüntü: her sahnenin ortasından kare al
    baslar = rapor["sahne_baslari"] + [rapor["sure"]]
    kareler = []
    for i in range(len(baslar) - 1):
        orta = (baslar[i] + baslar[i + 1]) / 2
        k = _kare(yol, orta)
        if k is None:
            hatalar.append(f"sahne {i}: kare okunamadı ({orta:.1f} sn)")
            continue
        tamam, kolcum, khatalar = gorsel_kontrol(k, en_az_kenar=0)  # küçültülmüş kare
        if not tamam:
            hatalar.append(f"sahne {i}: videodaki kare boş/bozuk görünüyor: {khatalar}")
        kareler.append(k)
    for i in range(1, len(kareler)):
        fark = ImageStat.Stat(ImageChops.difference(kareler[i - 1], kareler[i]).convert("L")).mean[0]
        if fark < 3:
            hatalar.append(f"sahne {i - 1} ve {i} aynı görüntü (donmuş video?)")

    # kaynak görseller
    olcum["gorsel_kaynaklari"] = [g["kaynak"] for g in rapor["gorseller"]]
    return not hatalar, hatalar, olcum
