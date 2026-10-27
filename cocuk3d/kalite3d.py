"""3D bölüm kalite kontrolü. Geçmeyen video yayın kuyruğuna girmez.

Kaynaklar: bitmiş MP4 (ffprobe/ffmpeg ile çözülür), Blender'ın kare kare ölçümü (meta.json),
kurgu bilgisi (kurgu.json) ve serinin kayıtlı karakter parmak izleri.
denetle() -> (tamam, hatalar, olcum)
"""
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from cocuk import kalite as kalite2d
from cocuk.gorsel import gorsel_kontrol

SR = 24000


def _video_akisi(yol, en, boy):
    """Kareleri küçük boyutta tek tek okur (uzun videoda bellek dostu)."""
    k_en, k_boy = (64, 114) if boy > en else (114, 64)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(yol), "-vf", f"scale={k_en}:{k_boy}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    boyut = k_en * k_boy * 3
    while True:
        b = p.stdout.read(boyut)
        if len(b) < boyut:
            break
        yield np.frombuffer(b, np.uint8).reshape(k_boy, k_en, 3).astype(np.float32)
    p.stdout.close()
    p.wait()


def _ses_zarfi(yol, fps):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(yol), "-vn", "-ac", "1", "-ar", str(SR),
                        "-f", "s16le", "-"], capture_output=True)
    s = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768
    p = SR // fps
    n = len(s) // p
    return np.sqrt(np.mean(s[: n * p].reshape(n, p) ** 2, axis=1)) if n else np.zeros(0)


def _korelasyon(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 5 or a.std() < 1e-6 or b.std() < 1e-6:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def denetle(mp4, is_dizini, seri_dizini):
    is_dizini, seri_dizini = Path(is_dizini), Path(seri_dizini)
    imza = is_dizini / "video.sha256"
    if imza.exists():  # ölçüm verisi bu videoya mı ait?
        import hashlib
        if hashlib.sha256(Path(mp4).read_bytes()).hexdigest() != imza.read_text().strip():
            return False, ["ölçüm verisi bu videoya ait değil (video.sha256 uyuşmuyor)"], {}
    kurgu = json.loads((is_dizini / "kurgu.json").read_text())
    meta = json.loads((is_dizini / "meta.json").read_text())
    prof, fps, n = kurgu["profil"], kurgu["fps"], kurgu["kare_say"]
    hatalar, olcum = [], {"animasyon_turu": "3d_blender", "profil": prof["ad"]}

    # ---- dosya
    try:
        bilgi = kalite2d._ffprobe(mp4)
    except Exception as e:
        return False, [str(e)], olcum
    v = [s for s in bilgi["streams"] if s["codec_type"] == "video"]
    a = [s for s in bilgi["streams"] if s["codec_type"] == "audio"]
    if not v or not a:
        return False, ["video ya da ses akışı yok"], olcum
    en, boy = int(v[0]["width"]), int(v[0]["height"])
    sure = float(bilgi["format"]["duration"])
    vs, as_ = float(v[0].get("duration", sure)), float(a[0].get("duration", sure))
    olcum.update({"cozunurluk": f"{en}x{boy}", "sure": round(sure, 2), "goruntu_sure": round(vs, 2),
                  "ses_sure": round(as_, 2), "beklenen_sure": round(n / fps, 2)})
    dikey = prof["boy"] > prof["en"]
    if (boy > en) != dikey:
        hatalar.append(f"yönelim yanlış: {en}x{boy}, profil {prof['ad']}")
    if abs(en / boy - prof["en"] / prof["boy"]) > 0.01:
        hatalar.append(f"en-boy oranı yanlış: {en}x{boy}")
    if abs(vs - n / fps) > 0.1:
        hatalar.append(f"görüntü süresi {vs:.2f} sn, beklenen {n / fps:.2f}")
    if abs(as_ - vs) > 0.12:
        hatalar.append(f"ses ({as_:.2f}) ve görüntü ({vs:.2f}) süreleri farklı")
    lo, hi = prof["sure"]
    if not lo <= sure <= hi:
        hatalar.append(f"süre {sure:.1f} sn; {prof['ad']} profili {lo:.0f}-{hi:.0f} sn ister")

    # ---- ses
    ses = kalite2d._ses_analizi(mp4)
    olcum["ses"] = ses
    if ses["ortalama_db"] is None or ses["ortalama_db"] < -35:
        hatalar.append(f"ses çok kısık/yok ({ses['ortalama_db']} dB)")
    if ses["tepe_db"] is not None and ses["tepe_db"] > -0.1:
        hatalar.append("ses kırpılıyor")
    if ses["uzun_sessizlik_sn"]:
        hatalar.append(f"boş ses bölümü: {ses['uzun_sessizlik_sn']} sn")
    km = kurgu["ses"]["konusma_muzik_db"]
    olcum["konusma_muzik_db"] = km
    if kurgu["ses"]["konusma_ornek"] == 0:
        olcum["konusma_muzik_db"] = "diyalog yok (uygulanmadı)"
    elif km is None or km < 10:
        hatalar.append(f"müzik konuşmayı bastırıyor (fark {km} dB, en az 10)")

    # ---- altyazı
    alt = json.loads((is_dizini / "altyazi.json").read_text())
    olcum["altyazi"] = alt
    if alt["gosterilmeyen"]:
        hatalar.append(f"{alt['gosterilmeyen']} kelime altyazıda görünmedi")
    if alt["en_uzun_bosluk_sn"] > 0.8:
        hatalar.append(f"konuşmada {alt['en_uzun_bosluk_sn']} sn altyazısız")

    # ---- görüntü akışı: siyah, donmuş, ayrıntısız kare
    farklar, parlak, onceki, ornek = [], [], None, []
    for i, k in enumerate(_video_akisi(mp4, en, boy)):
        parlak.append(float(k.mean()))
        farklar.append(float(np.abs(k - onceki).mean()) if onceki is not None else 999.0)
        onceki = k
        if i % (2 * fps) == fps:
            ornek.append((i, k))
    farklar = np.array(farklar)
    siyah = [i for i, p in enumerate(parlak) if p < 12]
    if siyah:
        hatalar.append(f"{len(siyah)} siyah kare (ilk: {siyah[0]})")
    en_uzun_donuk = akt = 0
    for f_ in farklar:
        akt = akt + 1 if f_ < 0.15 else 0
        en_uzun_donuk = max(en_uzun_donuk, akt)
    olcum["en_uzun_donuk_sn"] = round(en_uzun_donuk / fps, 2)
    if en_uzun_donuk / fps > 1.0:
        hatalar.append(f"görüntü {en_uzun_donuk / fps:.1f} sn donuk")
    for i, k in ornek:
        tamam, _, kh = gorsel_kontrol(Image.fromarray(k.astype(np.uint8)), en_az_kenar=0)
        if not tamam and "kontrast yok (düz/boş görsel)" in kh:
            hatalar.append(f"kare {i} boş görünüyor: {kh}")
    if len(farklar) != n:
        hatalar.append(f"karede eksik: {len(farklar)} / {n}")

    # ---- animasyon ölçümleri (meta)
    km_ = meta["kareler"]
    kesimler = []
    for c in kurgu["cekimler"]:
        b, s = c["bas_kare"], c["bas_kare"] + c["kare_say"]
        dilim = km_[b:s]
        ad = c["id"]
        # kaybolan karakter
        for h in c["hedef"]:
            if c["tip"] == "yakin":  # yakın çekimde el/ayak/gövde kadraj dışında olabilir; yüz şart
                oran = np.mean([fr["karakter"][h]["gorunen"]["bas"] for fr in dilim])
            else:
                oran = np.mean([fr["karakter"][h]["gorunur"] >= 5 / 6 for fr in dilim])  # 6 noktadan ≥5
            if oran < 0.9:
                hatalar.append(f"{ad}: '{h}' karelerin yalnız %{oran * 100:.0f}'inde kadrajda")
        # yer değiştirme
        if any(e in ("yuru", "kos") for e in c["eylemler"]):
            yer = max(np.linalg.norm(np.array(dilim[-1]["karakter"][h]["konum"][:2])
                                     - np.array(dilim[0]["karakter"][h]["konum"][:2])) for h in dilim[0]["karakter"])
            if yer < 0.25:
                hatalar.append(f"{ad}: yürüme eylemi var ama karakter {yer:.2f} m yer değiştirdi")
        # uzuv hareketi
        if c["eylemler"]:
            uzuv = max(float(np.std([np.array(fr["karakter"][h][u]) - np.array(fr["karakter"][h]["konum"])
                                     for fr in dilim], axis=0).max())
                       for h in dilim[0]["karakter"] for u in ("el.L", "el.R", "ayak.L", "ayak.R", "bas"))
            if uzuv < 0.01:
                hatalar.append(f"{ad}: uzuvlar hareket etmiyor (sapma {uzuv:.3f} m)")
        # eyleme özgü poz: el sallarken/zıplarken kalkan el gövdenin DIŞINDA olmalı
        # (ölçüm: kolları gövdeye gömülen hatalı rig 0.05/0.24 m, doğru rig 0.41/0.43 m)
        if {"el_salla", "zipla"} & set(c["eylemler"]):
            yana = 0.0
            for fr in dilim:
                for h, k in fr["karakter"].items():
                    for el in ("el.L", "el.R"):
                        if k[el][2] - k["konum"][2] > 0.5:
                            yana = max(yana, float(np.hypot(k[el][0] - k["govde"][0], k[el][1] - k["govde"][1])))
            if yana < 0.32:
                hatalar.append(f"{ad}: kalkan kol gövdenin içinde kalıyor (yana açılma {yana:.2f} m, en az 0.32)")
        if "zipla" in c["eylemler"]:
            havada = max(fr["karakter"][h]["konum"][2] for fr in dilim for h in fr["karakter"])
            if havada < 0.15:
                hatalar.append(f"{ad}: zıplama görünmüyor (yükseklik {havada:.2f} m)")
        # ağız: aşırı açılma ("sarkan dil" görünümü) — ölçüm: hatalı 5.7×, doğru ≤2.8×
        agiz_en = max(fr["karakter"][h]["agiz"] for fr in dilim for h in fr["karakter"])
        if agiz_en > 3.2:
            hatalar.append(f"{ad}: ağız aşırı açılıyor ({agiz_en:.1f}×, en çok 3.2×)")
        # kamera
        kam = np.array([fr["kamera"] for fr in dilim])
        yol = float(np.linalg.norm(np.diff(kam[:, :3], axis=0), axis=1).sum())
        donus = float(np.abs(kam[-1, 3:] - kam[0, 3:]).max())
        if c["hareket"] != "sabit" and yol < 0.08 and donus < 0.04:
            hatalar.append(f"{ad}: kamera hareketi '{c['hareket']}' görünmüyor (yol {yol:.2f} m)")
        # ışık
        if c["isik"] != c["isik_son"]:
            fark = abs(dilim[-1]["gunes"] - dilim[0]["gunes"])
            if fark < 0.2:
                hatalar.append(f"{ad}: ışık geçişi görünmüyor")
        if b > 0:
            kesimler.append(float(np.linalg.norm(np.array(km_[b]["kamera"][:3]) - np.array(km_[b - 1]["kamera"][:3]))))
    olcum["kamera_kesim_sicramalari_m"] = [round(x, 2) for x in kesimler]
    if kesimler and sum(1 for x in kesimler if x > 0.3) < len(kesimler) // 2:
        hatalar.append("çekim geçişlerinde kamera açısı değişmiyor (tek açı)")

    # ---- dudak senkronu (bitmiş dosyanın sesine göre) ve ses-görüntü senkronu
    zarf = _ses_zarfi(mp4, fps)
    olcum["dudak_korelasyon"] = {}
    for kim in meta["parmak_izi"]:
        idx = [f for s in kurgu["satirlar"] if s["kim"] == kim
               for f in range(int(s["bas"] * fps), min(n, int(s["son"] * fps)))]
        if not idx:
            continue
        idx = [f for f in idx if f < len(zarf)]  # ses biraz kısaysa eldeki kısımla ölç
        agiz = [km_[f]["karakter"][kim]["agiz"] for f in idx]
        r = _korelasyon(agiz, zarf[idx])
        olcum["dudak_korelasyon"][kim] = round(r, 2)
        if r < 0.5:
            hatalar.append(f"'{kim}' ağız hareketi konuşmayla eşleşmiyor (r={r:.2f})")

    # ---- karakter tutarlılığı (seri kaydı)
    kayit = seri_dizini / "karakter_izleri.json"
    izler = json.loads(kayit.read_text()) if kayit.exists() else {}
    olcum["parmak_izi"] = meta["parmak_izi"]
    for kim, iz in meta["parmak_izi"].items():
        if kim in izler and izler[kim] != iz:
            hatalar.append(f"'{kim}' modeli seri kaydından farklı (görünüş değişmiş)")
    return not hatalar, hatalar, olcum
