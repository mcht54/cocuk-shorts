"""Gemini (ücretsiz katman) çağrısı: iki kanalın içerik yazarları ortak kullanır.

Anahtar havuzu (2026-11-28): GEMINI_API_KEY, GEMINI_API_KEY_2 … _9 (ayrı Gmail hesaplarının ücretsiz anahtarları).
Günlük kotası dolan anahtar o model için o Google günü (TR 11:00'e kadar) atlanır: otonom/gemini-havuz.json
(yalnız sha256[:8] parmak izi). Model takma adları ("-latest") Google'ın yeni sürümlerine kendiliğinden geçer;
biri kaldırılırsa sıradaki denenir. Ücretsiz katmanın dakikalık sınırına takılmamak için çağrılar arası
bekleme vardır; 429/5xx'te artan beklemeyle yeniden denenir.
"""
import json
import os
import re
import time

import requests

from ortak import gemini_havuz as _gh

MODELLER = [m for m in os.environ.get("GEMINI_MODELLER", "").split(",") if m] or [
    "gemini-flash-latest", "gemini-flash-lite-latest"]
ARA_BEKLEME = float(os.environ.get("GEMINI_ARA_BEKLEME", "13"))
SINIR = int(os.environ.get("GEMINI_CAGRI_SINIRI", "100"))  # bir çalıştırmada en çok çağrı
CAGRI = 0
_son = 0.0


class GeminiYok(RuntimeError):
    """Anahtar yok, kota bitti ya da servis yanıt vermiyor: çağıran bu çalıştırmayı atlar."""


def _json_ayikla(metin):
    metin = metin.strip()
    if metin.startswith("```"):
        metin = re.sub(r"^```(json)?|```$", "", metin, flags=re.M).strip()
    return json.loads(metin)


def _ozet(metin):
    try:
        return json.loads(metin)["error"]["message"][:160]
    except (ValueError, KeyError, TypeError):
        return metin[:160]


HAVUZ_DOSYASI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "otonom", "gemini-havuz.json")


def anahtarlar():
    return _gh.anahtarlar()


def _gonder(model, govde, anahtar, zaman, yol="generateContent"):
    """Havuzun taşıyıcısı: çalıştırma başına çağrı sınırı + dakikalık sınıra takılmamak için çağrılar arası bekleme."""
    global CAGRI, _son
    if CAGRI >= SINIR:
        raise GeminiYok(f"çalıştırma başına çağrı sınırı ({SINIR}) doldu")
    bekle = ARA_BEKLEME - (time.time() - _son)
    if bekle > 0:
        time.sleep(bekle)
    CAGRI += 1
    _son = time.time()
    r = requests.post(f"{_gh.API}/models/{model}:{yol}", headers={"x-goog-api-key": anahtar}, json=govde, timeout=zaman)
    return r.status_code, r.text


def havuz(gonder=None):
    return _gh.Havuz(HAVUZ_DOSYASI, _gh.anahtarlar, gunluk=lambda m: print(f"    [gemini] {m}", flush=True),
                     gonder=gonder or _gonder)


def sor(istem, sicaklik=0.9, json_cikti=True):
    """İstemi gönderir; json_cikti ise ayrıştırılmış JSON, değilse metin döner."""
    if not anahtarlar():
        raise GeminiYok("GEMINI_API_KEY tanımlı değil")
    govde = {"contents": [{"parts": [{"text": istem}]}],
             "generationConfig": {"temperature": sicaklik}}
    if json_cikti:
        govde["generationConfig"]["responseMimeType"] = "application/json"
    son_hata = ""
    h = havuz()
    for model in MODELLER:
        for _ in range(2):  # yanıt ayrıştırılamazsa aynı modelle bir kez daha
            try:
                j = h.cagir(model, govde, zaman=180, deneme=4)
            except _gh.GunlukKota as e:  # bütün anahtarların günlük ücretsiz kotası dolu: sıradaki model
                son_hata = f"{model}: 429 {e}"
                _kota("gemini_metin")  # panel "Yapay zekâ" rozeti (2026-11-27)
                break
            except _gh.GeminiHatasi as e:
                son_hata = f"{model}: {e.kod} {e}"
                if e.kod in (400, 401, 403):
                    raise GeminiYok(son_hata) from e
                break  # 404 (model kaldırılmış) / geçici hata sürdü / dakikalık sınır: sıradaki model
            try:
                metin = j["candidates"][0]["content"]["parts"][0]["text"]
                return _json_ayikla(metin) if json_cikti else metin
            except (KeyError, IndexError, ValueError) as e:
                son_hata = f"{model}: yanıt ayrıştırılamadı ({e})"
    if son_hata and " 429 " in f" {son_hata} ":
        _kota("metin_yok")
    raise GeminiYok(f"Gemini yanıt vermedi: {son_hata}")


def _kota(tur):
    try:
        import pathlib
        from ortak.kota_kaydi import kaydet
        kaydet(pathlib.Path(__file__).resolve().parent.parent / "otonom", tur)
    except Exception:  # noqa: BLE001
        pass
