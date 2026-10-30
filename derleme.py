"""Haftalık uzun video: kalite kontrolünden geçmiş yatay bölümleri tek videoda birleştirir.

Adımlar (GitHub Actions'ta haftalik-uzun.yml çalıştırır):
  python derleme.py sec [--bolumler 1,2,3]   -> derlenecek bölüm dosyaları (JSON, GITHUB_OUTPUT'a)
  python derleme.py birlestir <parca_dizini>  -> cikti3d/derleme/*.mp4 + .rapor.json + kapak
  python derleme.py yukle                     -> YAYIN=acik ise yükler (UZUN_GIZLILIK, varsayılan private)

Her parça uret3d.py'nin kendi kalite kontrolünü geçmiş olmalı (rapor + video SHA256 eşleşir);
birleşik video ayrıca süre, siyah/donuk kare ve ses kontrolünden geçer. Geçmeyen yayımlanmaz.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cocuk import video

KOK = Path(__file__).resolve().parent
SERI = KOK / "seri" / "findik-ile-pamuk"
KAYIT = KOK / "yayin_kaydi.json"
CIKTI = KOK / "cikti3d" / "derleme"
EN_AZ_PARCA, EN_COK_PARCA = 3, 7
EN_AZ_SURE = 60.0


def ozet(metin):
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")
    print(metin, flush=True)


def kayitlar():
    return json.loads(KAYIT.read_text()) if KAYIT.exists() else []


def sec(bolum_nolari=None):
    """Elle verilen bölümler; yoksa Shorts'u yüklenmiş ama henüz derlemeye girmemiş en eski bölümler."""
    if bolum_nolari:
        secilen = [f"seri/findik-ile-pamuk/bolumler/b{int(n):03d}.json" for n in bolum_nolari]
    else:
        k = kayitlar()
        # gizli deneme derlemeleri sayılmaz: bölümleri herkese açık derlemeye yine girer
        derlenen = {b for x in k if x.get("profil") == "derleme" and x.get("durum") == "yuklendi"
                    and (x.get("youtube") or {}).get("privacyStatus") == "public" for b in x.get("parcalar", [])}
        secilen = []
        for x in k:
            if (x.get("profil") == "shorts" and x.get("durum") == "yuklendi"
                    and x["bolum"] not in derlenen and x["bolum"] not in secilen):
                secilen.append(x["bolum"])
        secilen = secilen[:EN_COK_PARCA]
    eksik = [b for b in secilen if not (KOK / b).exists()]
    if eksik:
        raise SystemExit(f"bölüm dosyası yok: {eksik}")
    if len(secilen) < EN_AZ_PARCA:
        ozet(f"Derleme için yeterli bölüm yok ({len(secilen)}/{EN_AZ_PARCA}); bu hafta uzun video çıkmaz.")
        secilen = []
    return secilen


def _sure(yol):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
                        "-of", "json", str(yol)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    akis = next(s for s in j["streams"] if "width" in s)
    return float(j["format"]["duration"]), (akis["width"], akis["height"])


def _sn(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def parcalari_topla(parca_dizini):
    """Kalite geçmiş ve videosu raporuyla eşleşen parçalar, bölüm sırasıyla."""
    parcalar, atlanan = [], []
    for rapor_yolu in sorted(Path(parca_dizini).rglob("*-uzun-*.rapor.json")):
        r = json.loads(rapor_yolu.read_text())
        mp4 = rapor_yolu.with_name(rapor_yolu.name.replace(".rapor.json", ".mp4"))
        sha = rapor_yolu.with_name(rapor_yolu.name.replace(".rapor.json", ".veri")) / "video.sha256"
        neden = None
        if not r.get("kalite_gecti"):
            neden = "kalite kontrolü geçmedi: " + "; ".join(r.get("hatalar", []))[:200]
        elif not mp4.exists():
            neden = "video dosyası yok"
        elif not sha.exists() or sha.read_text().strip() != hashlib.sha256(mp4.read_bytes()).hexdigest():
            neden = "video, kalite raporundaki SHA256 ile eşleşmiyor"
        if neden:
            atlanan.append((r["bolum"], neden))
            continue
        parcalar.append({"bolum": r["bolum"], "mp4": mp4, "rapor": r})
    parcalar.sort(key=lambda p: p["bolum"])
    # aynı bölümün birden çok denemesi varsa en sonuncusu
    tekil = {}
    for p in parcalar:
        tekil[p["bolum"]] = p
    return list(tekil.values()), atlanan


def denetle(mp4, beklenen_sure, boyut):
    """Birleşik videonun kendi kontrolü: süre, çözünürlük, siyah/donuk kare, ses."""
    hatalar = []
    sure, cozunurluk = _sure(mp4)
    if sure < EN_AZ_SURE:
        hatalar.append(f"süre {sure:.1f} sn < {EN_AZ_SURE:.0f} sn")
    if abs(sure - beklenen_sure) > 1.5:
        hatalar.append(f"süre {sure:.1f} sn, parçaların toplamı {beklenen_sure:.1f} sn")
    if cozunurluk != boyut:
        hatalar.append(f"çözünürlük {cozunurluk}, beklenen {boyut}")
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(mp4), "-vf",
                        "blackdetect=d=1.0:pix_th=0.08,freezedetect=n=0.001:d=4", "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    log = r.stderr
    siyah = re.findall(r"black_duration:([\d.]+)", log)
    donuk = re.findall(r"freeze_duration: ([\d.]+)", log)
    ses = re.search(r"mean_volume: (-?[\d.]+) dB", log)
    if siyah:
        hatalar.append(f"{len(siyah)} siyah aralık (en uzun {max(map(float, siyah)):.1f} sn)")
    if donuk:
        hatalar.append(f"{len(donuk)} donuk aralık (en uzun {max(map(float, donuk)):.1f} sn)")
    ortalama_ses = float(ses.group(1)) if ses else None
    if ortalama_ses is None or ortalama_ses < -40:
        hatalar.append(f"ses yok ya da çok kısık (ortalama {ortalama_ses} dB)")
    return hatalar, {"sure": round(sure, 2), "cozunurluk": f"{cozunurluk[0]}x{cozunurluk[1]}",
                     "ortalama_ses_db": ortalama_ses}


def kapak(mp4, saniye, baslik, cikti):
    """1280x720 kapak: bölümden bir kare + büyük başlık. YouTube sınırı 2 MB."""
    ham = cikti.with_suffix(".kare.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{saniye:.2f}", "-i", str(mp4),
                    "-frames:v", "1", str(ham)], check=True)
    img = Image.open(ham).convert("RGB")
    ham.unlink()
    # altyazı kuşağını (uzun profilde boyun ~%80'i) dışarıda bırak, karakterlere yaklaş
    en, boy = img.size
    k_boy = int(boy * 0.74)
    k_en = int(k_boy * 16 / 9)
    sol = (en - k_en) // 2
    img = img.crop((sol, 0, sol + k_en, k_boy)).resize((1280, 720), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(video.FONT, 104)
    satirlar, akt = [], ""
    for k in baslik.split():
        dd = (akt + " " + k).strip()
        if d.textlength(dd, font=font) > 1180 and akt:
            satirlar.append(akt)
            akt = k
        else:
            akt = dd
    satirlar.append(akt)
    y = 720 - 30 - len(satirlar) * 112
    for s in satirlar:
        w = d.textlength(s, font=font)
        d.text(((1280 - w) / 2, y), s, font=font, fill=(255, 255, 255),
               stroke_width=11, stroke_fill=(232, 72, 120))
        y += 112
    img.save(cikti, "JPEG", quality=88)
    return cikti


def birlestir(parca_dizini):
    parcalar, atlanan = parcalari_topla(parca_dizini)
    for b, neden in atlanan:
        ozet(f"- atlandı {b}: {neden}")
    if len(parcalar) < EN_AZ_PARCA:
        ozet(f"Kaliteyi geçen parça sayısı {len(parcalar)} < {EN_AZ_PARCA}; derleme yapılmadı.")
        return 1
    boyutlar = {_sure(p["mp4"])[1] for p in parcalar}
    if len(boyutlar) != 1:
        ozet(f"Parçaların çözünürlüğü farklı: {boyutlar}; derleme yapılmadı.")
        return 1
    boyut = boyutlar.pop()

    CIKTI.mkdir(parents=True, exist_ok=True)
    zaman = datetime.now().strftime("%Y%m%d-%H%M")
    mp4 = CIKTI / f"derleme-{zaman}.mp4"
    girdiler, bolumler, t = [], [], 0.0
    for p in parcalar:
        sure = _sure(p["mp4"])[0]
        girdiler += ["-i", str(p["mp4"])]
        bolum = json.loads((KOK / p["bolum"]).read_text())
        bolumler.append({"bolum": p["bolum"], "baslik": bolum["baslik"], "bas": round(t, 2),
                         "sure": round(sure, 2), "deger": bolum.get("deger")})
        t += sure
    n = len(parcalar)
    filtre = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *girdiler, "-filter_complex", filtre,
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                    str(mp4)], check=True)

    hatalar, olcum = denetle(mp4, t, boyut)
    seri = json.loads((SERI / "seri.json").read_text())
    adlar = [b["baslik"] for b in bolumler]
    baslik = f"{seri['seri_adi']} | {n} Masal Bir Arada: {', '.join(adlar)}"
    if len(baslik) > 88:
        baslik = f"{seri['seri_adi']} | {n} Masal Bir Arada | 3D Çocuk Çizgi Filmi"
    bolum_listesi = "\n".join(f"{_sn(b['bas'])} {b['baslik']}" for b in bolumler)
    aciklama = (f"{seri['seri_adi']} serisinden {n} kısa masal arka arkaya. Her bölüm bir değeri işler: "
                + ", ".join(b["deger"] for b in bolumler if b["deger"]) + ".\n\n"
                "Bölümler:\n" + bolum_listesi + "\n\nÖzgün 3D çizgi film; 3-7 yaş için.")
    etiketler = ["çocuk çizgi filmi", "masal", "3D animasyon", "okul öncesi", "çizgi film türkçe",
                 seri["seri_adi"], "uyku öncesi masal"]
    kapak_yolu = kapak(parcalar[0]["mp4"], min(6.0, bolumler[0]["sure"] * 0.4),
                       f"{n} Masal Bir Arada", mp4.with_suffix(".kapak.jpg"))
    rapor = {"profil": "derleme", "video": str(mp4.relative_to(KOK)), "kapak": str(kapak_yolu.relative_to(KOK)),
             "kalite_gecti": not hatalar, "hatalar": hatalar, "olcum": olcum, "bolumler": bolumler,
             "atlanan": [{"bolum": b, "neden": x} for b, x in atlanan],
             "youtube": {"baslik": baslik, "aciklama": aciklama, "etiketler": etiketler},
             "sha256": hashlib.sha256(mp4.read_bytes()).hexdigest()}
    mp4.with_suffix(".rapor.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=1))
    ozet(f"### Derleme: {n} bölüm, {olcum['sure']} sn, {olcum['cozunurluk']}")
    ozet(bolum_listesi.replace("\n", "  \n"))
    if hatalar:
        ozet("Kalite KALDI; yayımlanmayacak:")
        for h in hatalar:
            ozet(f"- {h}")
        return 1
    ozet("Kalite GEÇTİ")
    return 0


def kapak_yukle(video_id, kapak_yolu, anahtar):
    import requests
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                      params={"videoId": video_id}, headers={"Authorization": f"Bearer {anahtar}",
                                                             "Content-Type": "image/jpeg"},
                      data=Path(kapak_yolu).read_bytes(), timeout=60)
    return r.status_code, r.text[:300]


def yukle():
    raporlar = sorted(CIKTI.glob("derleme-*.rapor.json"))
    if not raporlar:
        ozet("Yüklenecek derleme yok.")
        return 1
    rapor = json.loads(raporlar[-1].read_text())
    mp4 = KOK / rapor["video"]
    if not rapor["kalite_gecti"] or hashlib.sha256(mp4.read_bytes()).hexdigest() != rapor["sha256"]:
        ozet("Derleme kaliteyi geçmedi ya da video raporla eşleşmiyor; yüklenmedi.")
        return 1
    kayit = {"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"), "profil": "derleme",
             "bolum": "derleme", "parcalar": [b["bolum"] for b in rapor["bolumler"]], "durum": "uretildi",
             "sure": rapor["olcum"]["sure"]}
    if os.environ.get("YAYIN") == "acik":
        from cocuk import youtube
        gizlilik = os.environ.get("YT_GIZLILIK", "private")
        anahtar = youtube.erisim_anahtari()
        vid, durum = youtube.yukle(mp4, rapor["youtube"], anahtar, gizlilik=gizlilik,
                                   acik_onay=os.environ.get("YT_HERKESE_ACIK_ONAY") == "evet",
                                   shorts=False, sentetik=False)
        kayit.update(durum="yuklendi", video_id=vid, youtube=durum)
        ozet(f"YouTube: https://youtube.com/watch?v={vid} — {durum}")
        kod, metin = kapak_yukle(vid, KOK / rapor["kapak"], anahtar)
        kayit["kapak"] = "yuklendi" if kod == 200 else f"yuklenemedi ({kod})"
        ozet("Kapak resmi yüklendi." if kod == 200 else
             f"Kapak resmi yüklenemedi ({kod}); kanalın telefon doğrulaması gerekebilir. {metin}")
    else:
        ozet("Yayın kapalı (YAYIN != acik): derleme yalnız üretildi, Actions 'Artifacts' altında.")
    k = kayitlar()
    k.append(kayit)
    KAYIT.write_text(json.dumps(k, ensure_ascii=False, indent=1))
    return 0


def main():
    ap = argparse.ArgumentParser()
    alt = ap.add_subparsers(dest="komut", required=True)
    s = alt.add_parser("sec")
    s.add_argument("--bolumler", default="")
    b = alt.add_parser("birlestir")
    b.add_argument("parca_dizini")
    alt.add_parser("yukle")
    a = ap.parse_args()
    if a.komut == "sec":
        secilen = sec([n for n in a.bolumler.replace(" ", "").split(",") if n])
        cikti = os.environ.get("GITHUB_OUTPUT")
        if cikti:
            with open(cikti, "a") as f:
                f.write(f"bolumler={json.dumps(secilen)}\nadet={len(secilen)}\n")
        print(json.dumps(secilen))
        return 0
    if a.komut == "birlestir":
        return birlestir(a.parca_dizini)
    return yukle()


if __name__ == "__main__":
    sys.exit(main())
