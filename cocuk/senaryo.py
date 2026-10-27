"""Gemini (ücretsiz katman) ile çocuk Shorts senaryosu yazar ve güvenlik denetiminden geçirir."""
import json
import os
import re
import time

import requests

from .cizim import KATALOG, ORTAMLAR

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
CAGRI = 0             # bu çalıştırmadaki Gemini çağrı sayısı
GUNLUK_SINIR = 30     # calistir.py bugünkü kullanımı düşerek ayarlar

TURLER = {
    "masal": (
        "3-7 yaş için 40-50 saniyelik KISA MASAL. Hayvan ya da sevimli karakterler, tek bir net "
        "değer (paylaşmak, dürüstlük, cesaret, yardımlaşma, sabır, özür dilemek, temizlik vb.). "
        "İlk cümle merak uyandırsın. Son sahne değeri tek cümleyle söylesin ve çocuğa sıcak bir "
        "soru sorsun. Korku, kötü karakter, ceza, tehlike, kayboluş YOK."),
    "egitici": (
        "2-5 yaş için 35-45 saniyelik EĞİTİCİ video: renkler, sayılar (1-10), şekiller, hayvan "
        "sesleri, meyveler, taşıtlar, zıt kavramlar, duygular gibi tek bir küçük kavram. Kısa, "
        "tekrarlı, çocuğun yüksek sesle söyleyeceği cümleler ('Hadi söyle: ...'). Son sahne "
        "çocuğu etrafında bir şey bulmaya/yapmaya davet etsin."),
    "hayvan": (
        "5-10 yaş için 35-45 saniyelik 'Biliyor muydun?' HAYVAN BİLGİLERİ videosu. Tek bir hayvan, "
        "4-5 şaşırtıcı ama BİLİMSEL OLARAK KESİN ve yaygın kabul gören bilgi. Emin olmadığın "
        "bilgiyi yazma. Avlanma/kan/ölüm ayrıntısı yok. Son sahne çocuğa bir soru sorsun."),
}

YAZIM_ISTEMI = """Sen Türkçe çocuk YouTube Shorts kanalı için senarist ve yönetmensin.
Görev: {tarif}

Kurallar:
- Dil: sade, akıcı, doğru Türkçe; çocuğa doğrudan hitap. Toplam 85-115 kelime.
- 6-7 sahne. Her sahnenin "metin"i 1-2 kısa cümle (en fazla 20 kelime).
- Her sahnenin "gorsel"i İNGİLİZCE, tek sahnelik çizim tarifi (karakter, eylem, ortam). Yazı/harf istemi yok.
- "karakter_tarifi": ana karakter varsa İngilizce kısa görünüş tarifi (her görselde aynı kalsın), yoksa "".
- "karakter_ogesi": ana karakter şu listeden hangisiyse onun anahtarı, yoksa "": {hayvanlar}
- Her sahnede "ortam": şunlardan biri: {ortamlar}
- Her sahnede "ogeler": sahnede görünen 1-4 şeyin anahtarı, YALNIZCA şu listeden: {ogeler}
- "ekran_basligi": videonun ilk 3 saniyesinde ekranda yazacak en fazla 5 kelimelik merak uyandıran başlık.
- "baslik": YouTube başlığı, en fazla 70 karakter, 1 emoji, sonunda " | " ile tür ("Kısa Masal", "Okul Öncesi", "Biliyor muydun?").
- "aciklama": 2-3 cümlelik ebeveyne yönelik açıklama.
- "etiketler": 8-12 Türkçe etiket.
- "konu": tek satırlık konu özeti (tekrarı önlemek için kaydedilir).
- Daha önce işlenen şu konuları TEKRARLAMA: {gecmis}

Yalnızca şu JSON'u döndür:
{{"konu": "", "baslik": "", "ekran_basligi": "", "aciklama": "", "etiketler": [], "karakter_tarifi": "", "karakter_ogesi": "", "sahneler": [{{"metin": "", "gorsel": "", "ortam": "", "ogeler": []}}]}}"""

DENETIM_ISTEMI = """Aşağıdaki senaryo 2-10 yaş çocuklara yönelik bir YouTube videosunda yayınlanacak.
Titizlikle denetle. Şunlardan BİRİ bile varsa uygun=false:
- korku, şiddet, yaralanma, ölüm, tehlikeli/taklit edilmesi riskli davranış (ör. ateş, yükseklik, ilaç, yabancıya gitmek)
- cinsellik, argo, aşağılama, ayrımcılık, marka/ürün tanıtımı, din/siyaset
- yanlış ya da şüpheli bilgi (özellikle hayvan bilgilerinde emin olmadığın her iddia)
- dil bilgisi hatası ya da anlamsız cümle
JSON döndür: {{"uygun": true/false, "neden": "kısa açıklama"}}

Senaryo:
{senaryo}"""

YASAK = re.compile(r"\b(ölüm|öldü|ölmüş|ölecek|öldür|kanlı|kanama|bıçak|silah|tüfek|canavar|"
                   r"hayalet|cadı|korkunç|dehşet|dövdü|dövmek|yaralan)", re.I)


def _gemini(istem, sicaklik):
    global CAGRI
    anahtar = os.environ.get("GEMINI_API_KEY")
    if not anahtar:
        raise RuntimeError("GEMINI_API_KEY tanımlı değil; senaryo yazılamaz")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    govde = {"contents": [{"parts": [{"text": istem}]}],
             "generationConfig": {"temperature": sicaklik, "responseMimeType": "application/json"}}
    for deneme in range(4):
        if CAGRI >= GUNLUK_SINIR:
            raise RuntimeError(f"Gemini günlük çağrı sınırına ulaşıldı ({GUNLUK_SINIR})")
        CAGRI += 1
        r = requests.post(url, params={"key": anahtar}, json=govde, timeout=120)
        if r.ok:
            metin = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(metin)
        if r.status_code in (429, 500, 503):
            time.sleep(20 * (deneme + 1))
            continue
        raise RuntimeError(f"Gemini hatası {r.status_code}: {r.text[:300]}")
    raise RuntimeError("Gemini kotası/servisi yanıt vermedi")


def _gecerli(s):
    sahneler = s.get("sahneler") or []
    if not (5 <= len(sahneler) <= 8):
        return "sahne sayısı uygun değil"
    if any(not x.get("metin") or not x.get("gorsel") for x in sahneler):
        return "boş sahne"
    if not s.get("baslik") or len(s["baslik"]) > 95:
        return "başlık uygun değil"
    tum = " ".join(x["metin"] for x in sahneler)
    if YASAK.search(tum) or YASAK.search(s["baslik"]):
        return "yasaklı kelime"
    if not 60 <= len(tum.split()) <= 140:
        return "uzunluk uygun değil"
    return None


def yaz(tur, gecmis_konular, deneme_sayisi=4):
    for _ in range(deneme_sayisi):
        s = _gemini(YAZIM_ISTEMI.format(
            tarif=TURLER[tur], gecmis="; ".join(gecmis_konular[-80:]) or "yok",
            hayvanlar=", ".join(k for k, v in KATALOG.items() if v[2] == "hayvan"),
            ortamlar=", ".join(ORTAMLAR), ogeler=", ".join(KATALOG)), 1.0)
        # listede olmayan öğe/ortam adlarını ayıkla (yerel çizim yalnız bunları tanır)
        for sahne in s.get("sahneler") or []:
            sahne["ogeler"] = [o for o in sahne.get("ogeler") or [] if o in KATALOG]
            if sahne.get("ortam") not in ORTAMLAR:
                sahne.pop("ortam", None)
        if s.get("karakter_ogesi") not in KATALOG:
            s["karakter_ogesi"] = ""
        hata = _gecerli(s)
        if hata:
            print("senaryo reddedildi:", hata, flush=True)
            continue
        denetim = _gemini(DENETIM_ISTEMI.format(senaryo=json.dumps(s, ensure_ascii=False)), 0.1)
        if denetim.get("uygun") is True:
            s["tur"] = tur
            return s
        print("güvenlik denetimi reddetti:", denetim.get("neden"), flush=True)
    raise RuntimeError("Uygun senaryo üretilemedi; bu tur atlandı")
