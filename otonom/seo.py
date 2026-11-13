"""Minik Masal Evi yükleme bilgisi (başlık, açıklama, etiket, hashtag) — arama ve öneri için tek kaynak.

2026-11-13 kullanıcı: "videoların SEO uyumlu olması, keşfete düşmesi konusunda daha titiz çalış". Kurallar:
- Başlık: anne babanın aradığı ana kelime BAŞTA (YouTube ve mobil ~40-60 karakterden sonrasını keser),
  Shorts'ta "#shorts" dahil en çok 100 karakter, her video benzersiz.
- Açıklama: ilk 120 karakter aramada görünür → ana kelimeler ilk cümlede; doğal cümleler (kelime yığını
  YouTube'da spam sayılır), kanal adı, tam 3 hashtag (ilk 3'ü başlığın üstünde görünür; 15'ten fazlası
  hepsini geçersiz kılar).
- Etiketler: önce videoya özel, sonra genel; toplam 500 karakter sınırının altında.
- İngilizce dersleri: Türkçe aramalar ("ingilizce renkler", "apple ne demek") + İngilizce yerelleştirme
  (en başlık/açıklama) ile "learn english for kids" aramalarında da görünür.
`denetle` yüklemeden önce çalışır; sorun varsa yükleme yapılmaz değil, düzeltilmiş bilgi kullanılır ve
sorun özete yazılır (yayın durmasın).
"""
import re

KANAL = "Minik Masal Evi"
SERI = "Fındık ile Pamuk"
KANAL_URL = "https://www.youtube.com/@minikmasalevitv"
ETIKET_SINIRI = 480
BASLIK_SINIRI = 100

MASAL_ANAHTAR = ["çizgi film", "masal", "çocuk"]
MASAL_ETIKET = ["çizgi film", "çocuk çizgi filmi", "türkçe çizgi film", "masal", "masal dinle",
                "çocuk masalları", "eğitici çizgi film", "okul öncesi", "3D animasyon", "uyku masalı",
                "değerler eğitimi", SERI, KANAL]
MASAL_HASHTAG = ["#çizgifilm", "#masal", "#çocukmasalları"]

INGILIZCE_ANAHTAR = ["ingilizce"]
INGILIZCE_ETIKET = ["çocuklar için ingilizce", "ingilizce öğreniyorum", "ingilizce kelimeler",
                    "okul öncesi ingilizce", "ingilizce çizgi film", "eğlenceli ingilizce", "ilkokul ingilizce",
                    "learn english for kids", "english for kids", "kids vocabulary", SERI, KANAL]
INGILIZCE_HASHTAG = ["#ingilizce", "#çocuklariçiningilizce", "#ingilizceöğreniyorum"]


def _etiketler(oncelikli, genel):
    out, toplam = [], 0
    for e in oncelikli + genel:
        e = re.sub(r"\s+", " ", str(e)).strip().strip("#")
        if not e or e.lower() in {x.lower() for x in out} or "<" in e or ">" in e:
            continue
        if toplam + len(e) + 2 > ETIKET_SINIRI:  # YouTube etiket sınırı 500 (virgül/tırnak payıyla)
            continue
        out.append(e)
        toplam += len(e) + 2
    return out


def _kelime_listesi(bolum, adet=3):
    return [k["en"] for k in bolum.get("kelimeler", [])][:adet]


def _bas_harf(s):
    return s[:1].upper() + s[1:]


def masal_shorts(bolum):
    """Fındık ile Pamuk masal Shorts'u."""
    yt = bolum.get("youtube", {})
    ad = bolum["baslik"]
    baslik = f"{ad} | {SERI} | Çocuk Çizgi Filmi"
    if len(baslik) > 88:
        baslik = f"{ad} | {SERI} Çizgi Film"
    giris = re.sub(r"\s*Bu bölümün değeri:[^.]*\.", "", yt.get("aciklama") or "").strip()  # aşağıda ayrıca var
    deger = bolum.get("deger")
    aciklama = "\n\n".join(x for x in [
        f"{ad} — {SERI} çizgi film masalı. {giris}".strip(),
        (f"Bu masalın değeri: {deger}. Çocuğunuzla izledikten sonra sorun: Sen olsan ne yapardın?" if deger else ""),
        f"{SERI}, 3-7 yaş çocuklar için özgün Türkçe 3D çizgi film ve masal serisi. Meraklı sincap Fındık ile "
        f"yumuşak kalpli tavşan Pamuk her bölümde yeni bir macera yaşar ve bir değer öğretir.",
        f"Yeni masallar her gün {KANAL}'nde: {KANAL_URL}",
        " ".join(MASAL_HASHTAG),
    ] if x)
    ozel = [e for e in yt.get("etiketler", []) if e not in MASAL_ETIKET]
    return {"baslik": baslik, "aciklama": aciklama,
            "etiketler": _etiketler([ad, f"{ad} çizgi film"] + MASAL_ETIKET[:6] + ozel, MASAL_ETIKET[6:]),
            "hazir_aciklama": True}


def ingilizce_shorts(bolum):
    """Fındık ile Pamuk İngilizce dersi Shorts'u (bolum: konu, konu_en, kelimeler[{en, tr}])."""
    konu = bolum.get("konu") or bolum["baslik"]
    kel = _kelime_listesi(bolum)
    kel_metin = ", ".join(_bas_harf(k) for k in kel)
    baslik = f"İngilizce {konu}: {kel_metin} | Çocuklar için İngilizce"
    while len(baslik) > 88 and len(kel) > 1:  # "#shorts" payı
        kel = kel[:-1]
        kel_metin = ", ".join(_bas_harf(k) for k in kel)
        baslik = f"İngilizce {konu}: {kel_metin} | Çocuklar için İngilizce"
    if len(baslik) > 88:
        baslik = f"İngilizce {konu} | Çocuklar için İngilizce"[:88]
    sozluk = "\n".join(f"• {k['en']} = {k['tr']}" for k in bolum.get("kelimeler", []))
    aciklama = "\n\n".join(x for x in [
        f"Çocuklar için İngilizce: {SERI} ile İngilizce {konu.lower()} öğreniyoruz! "
        f"Bu derste {len(bolum.get('kelimeler', []))} yeni kelime var; her kelimeyi duyun, ekranda görün ve "
        f"Fındık ile birlikte tekrar edin.",
        "Bugünün kelimeleri:\n" + sozluk if sozluk else "",
        "Okul öncesi ve ilkokul çocukları için eğlenceli İngilizce kelimeler: kısa, tekrarlı, yerli İngilizce "
        "telaffuzla. Ebeveynlere öneri: videodan sonra kelimeleri günlük hayatta birlikte söyleyin.",
        f"Her gün yeni bir İngilizce dersi {KANAL}'nde: {KANAL_URL}",
        " ".join(INGILIZCE_HASHTAG),
    ] if x)
    ozel = [f"ingilizce {konu.lower()}", f"çocuklar için ingilizce {konu.lower()}"]
    ozel += [f"{k['en']} ne demek" for k in bolum.get("kelimeler", [])[:3]]
    ozel += [f"{k['tr']} ingilizcesi" for k in bolum.get("kelimeler", [])[:3]]
    if bolum.get("konu_en"):
        ozel.append(f"{bolum['konu_en'].lower()} in english")
    meta = {"baslik": baslik, "aciklama": aciklama,
            "etiketler": _etiketler(ozel + INGILIZCE_ETIKET[:5], INGILIZCE_ETIKET[5:]),
            "hazir_aciklama": True}
    if bolum.get("konu_en"):
        kel_en = ", ".join(_bas_harf(k) for k in _kelime_listesi(bolum))
        meta["localizations"] = {"en": {
            "title": f"Learn {bolum['konu_en']} in English for Kids: {kel_en} | Fındık and Pamuk"[:95],
            "description": (f"Learn {bolum['konu_en'].lower()} in English with Fındık the squirrel and Pamuk the "
                            f"bunny! Words: {', '.join(_kelime_listesi(bolum, 10))}. Short, repeat-after-me "
                            f"English vocabulary for preschool kids.\n\n#learnenglish #englishforkids #kidsvocabulary")}}
    return meta


def derleme(tur, seri_adi, bolumler, dakika, bolum_listesi):
    """Uzun derleme videosunun bilgisi. bolumler: [{"baslik", "deger", "dosya"(dict bölüm)}]."""
    n = len(bolumler)
    if tur == "ingilizce":
        konular = []
        for b in bolumler:
            k = b["dosya"].get("konu") or b["baslik"]
            if k not in konular:
                konular.append(k)
        baslik = f"Çocuklar için İngilizce | {n} Ders, {dakika} Dakika: {', '.join(konular)} | {seri_adi}"
        if len(baslik) > 95:
            baslik = f"Çocuklar için İngilizce | {n} Ders, {dakika} Dakika | İngilizce Kelimeler | {seri_adi}"
        tum = [k for b in bolumler for k in b["dosya"].get("kelimeler", [])]
        sozluk = ", ".join(f"{k['en']} ({k['tr']})" for k in tum)
        aciklama = "\n\n".join([
            f"Çocuklar için İngilizce: {seri_adi} ile {n} kısa İngilizce dersi arka arkaya, {dakika} dakika. "
            f"Konular: {', '.join(konular).lower()}. Her kelimeyi duyun, ekranda görün, tekrar edin.",
            "Bölümler:\n" + bolum_listesi,
            "Bu videodaki İngilizce kelimeler: " + sozluk if sozluk else "",
            "Okul öncesi ve ilkokul çocukları için yerli İngilizce telaffuzlu, tekrarlı ve eğlenceli kelime "
            f"dersleri. Her gün yeni ders {KANAL}'nde: {KANAL_URL}",
            " ".join(INGILIZCE_HASHTAG)])
        ozel = [f"ingilizce {k.lower()}" for k in konular] + ["ingilizce dersleri çocuklar için",
                                                               "ingilizce kelimeler çocuklar için"]
        return {"baslik": baslik, "aciklama": aciklama, "hazir_aciklama": True,
                "etiketler": _etiketler(ozel + INGILIZCE_ETIKET[:6], INGILIZCE_ETIKET[6:])}
    adlar = [b["baslik"] for b in bolumler]
    if tur == "karisik":
        baslik = f"Uyku Öncesi Masallar | {seri_adi} | {n} Masal, {dakika} Dakika | 3D Çizgi Film"
        ozel = ["uyku öncesi masallar", "uyku masalı", "uzun çizgi film", "masal dinle uyku"]
    else:
        baslik = f"{seri_adi} | {n} Masal Bir Arada: {', '.join(adlar)}"
        if len(baslik) > 88:
            baslik = f"{seri_adi} | {n} Masal Bir Arada | {dakika} Dakika Çocuk Çizgi Filmi"
        ozel = ["çizgi film izle", "uzun çizgi film", "masallar bir arada"]
    degerler = ", ".join(b["deger"] for b in bolumler if b.get("deger"))
    aciklama = "\n\n".join(x for x in [
        f"{seri_adi} çizgi film masalları: {n} masal arka arkaya, {dakika} dakika. "
        + (f"Her masal bir değer öğretir: {degerler}." if degerler else ""),
        "Bölümler:\n" + bolum_listesi,
        f"{seri_adi}, 3-7 yaş çocuklar için özgün Türkçe 3D çizgi film ve masal serisi. "
        f"Yeni masallar her gün {KANAL}'nde: {KANAL_URL}",
        " ".join(MASAL_HASHTAG)] if x)
    return {"baslik": baslik, "aciklama": aciklama, "hazir_aciklama": True,
            "etiketler": _etiketler(ozel + adlar[:5] + MASAL_ETIKET[:6], MASAL_ETIKET[6:])}


def denetle(meta, shorts=True, onceki_basliklar=()):
    """Yükleme öncesi SEO denetimi: sorun listesi (boş = uygun)."""
    h = []
    baslik, aciklama = meta.get("baslik", ""), meta.get("aciklama", "")
    tam = baslik + (" #shorts" if shorts and "#shorts" not in baslik.lower() else "")
    if not baslik.strip():
        h.append("başlık boş")
    if len(tam) > BASLIK_SINIRI:
        h.append(f"başlık {len(tam)} karakter (> {BASLIK_SINIRI})")
    if "<" in baslik or ">" in baslik:
        h.append("başlıkta < > var (YouTube reddeder)")
    ilk = baslik[:60].lower()
    if not any(a in ilk for a in MASAL_ANAHTAR + INGILIZCE_ANAHTAR + [SERI.lower()]):
        h.append("başlığın ilk 60 karakterinde ana arama kelimesi yok")
    if baslik.strip().lower() in {b.strip().lower() for b in onceki_basliklar if b}:
        h.append("başlık daha önce yüklenen bir videoyla aynı")
    if len(aciklama) < 200:
        h.append(f"açıklama kısa ({len(aciklama)} karakter < 200)")
    if not any(a in aciklama[:150].lower() for a in MASAL_ANAHTAR + INGILIZCE_ANAHTAR):
        h.append("açıklamanın ilk 150 karakterinde ana kelime yok")
    etiketler = re.findall(r"#\w+", aciklama)
    if not 1 <= len(etiketler) <= 15:
        h.append(f"açıklamada {len(etiketler)} hashtag (1-15 olmalı; 3 önerilir)")
    if len(aciklama) > 4900:
        h.append("açıklama 4900 karakteri aşıyor")
    toplam = sum(len(e) + 2 for e in meta.get("etiketler", []))
    if toplam > 500:
        h.append(f"etiketler {toplam} karakter (> 500)")
    if len(meta.get("etiketler", [])) < 5:
        h.append("5'ten az etiket")
    return h
