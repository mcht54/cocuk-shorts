"""Gemini (ücretsiz katman) çağrısı: iki kanalın içerik yazarları ortak kullanır.

Anahtar: GEMINI_API_KEY. Model takma adları ("-latest") Google'ın yeni sürümlerine kendiliğinden geçer;
biri kaldırılırsa sıradaki denenir. Ücretsiz katmanın dakikalık sınırına takılmamak için çağrılar arası
bekleme vardır; 429/5xx'te artan beklemeyle yeniden denenir.
"""
import json
import os
import re
import time

import requests

MODELLER = [m for m in os.environ.get("GEMINI_MODELLER", "").split(",") if m] or [
    "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"]
ARA_BEKLEME = float(os.environ.get("GEMINI_ARA_BEKLEME", "7"))
SINIR = int(os.environ.get("GEMINI_CAGRI_SINIRI", "60"))  # bir çalıştırmada en çok çağrı
CAGRI = 0
_son = 0.0


class GeminiYok(RuntimeError):
    """Anahtar yok, kota bitti ya da servis yanıt vermiyor: çağıran bu çalıştırmayı atlar."""


def _json_ayikla(metin):
    metin = metin.strip()
    if metin.startswith("```"):
        metin = re.sub(r"^```(json)?|```$", "", metin, flags=re.M).strip()
    return json.loads(metin)


def sor(istem, sicaklik=0.9, json_cikti=True):
    """İstemi gönderir; json_cikti ise ayrıştırılmış JSON, değilse metin döner."""
    global CAGRI, _son
    anahtar = os.environ.get("GEMINI_API_KEY")
    if not anahtar:
        raise GeminiYok("GEMINI_API_KEY tanımlı değil")
    govde = {"contents": [{"parts": [{"text": istem}]}],
             "generationConfig": {"temperature": sicaklik}}
    if json_cikti:
        govde["generationConfig"]["responseMimeType"] = "application/json"
    son_hata = ""
    for model in MODELLER:
        for deneme in range(4):
            if CAGRI >= SINIR:
                raise GeminiYok(f"çalıştırma başına çağrı sınırı ({SINIR}) doldu")
            bekle = ARA_BEKLEME - (time.time() - _son)
            if bekle > 0:
                time.sleep(bekle)
            CAGRI += 1
            _son = time.time()
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": anahtar}, json=govde, timeout=180)
            except requests.RequestException as e:
                son_hata = str(e)
                time.sleep(15 * (deneme + 1))
                continue
            if r.ok:
                try:
                    metin = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return _json_ayikla(metin) if json_cikti else metin
                except (KeyError, IndexError, ValueError) as e:
                    son_hata = f"{model}: yanıt ayrıştırılamadı ({e})"
                    continue
            son_hata = f"{model}: {r.status_code} {r.text[:200]}"
            if r.status_code == 404:  # model kaldırılmış: sıradakine geç
                break
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(30 * (deneme + 1))
                continue
            if r.status_code in (400, 401, 403):
                raise GeminiYok(son_hata)
    raise GeminiYok(f"Gemini yanıt vermedi: {son_hata}")
