"""Yapay zekâ kota kaydı (2026-11-27, Mücahit: "kota ve limit olunca panele aktar, oradan takip edeceğim").
Ücretsiz katman dolunca hat buraya not düşer (rakam/anahtar YAZILMAZ); panel senkronu bunu "Yapay zekâ" rozeti olarak gönderir.
Gemini'nin ücretsiz günlük kotası her gün 11:00'de (TR) yenilenir; ondan önceki kayıtlar rozeti etkilemez. Ücretliye geçilmez.
Türler: gemini_metin (bir model doldu, sıradakiler/yedek denenir), gemini_ses (seslendirme kotası; yedeği yok),
groq (Groq yedeği de doldu), metin_yok (hiçbir model metin yazamadı)."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

TR = dt.timezone(dt.timedelta(hours=3))


def _yol(kok):
    return pathlib.Path(kok) / "kota.json"


def kaydet(kok, tur: str) -> None:
    try:
        p = _yol(kok)
        v = json.loads(p.read_text()) if p.exists() else {}
        v[tur] = dt.datetime.now(TR).isoformat(timespec="seconds")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(v, ensure_ascii=False, indent=1))
    except Exception:  # noqa: BLE001
        pass


def rozet(kok) -> dict:
    simdi = dt.datetime.now(TR)
    bas = simdi.replace(hour=11, minute=0, second=0, microsecond=0)
    if simdi < bas:
        bas -= dt.timedelta(days=1)
    try:
        v = json.loads(_yol(kok).read_text())
    except Exception:  # noqa: BLE001
        v = {}
    son = {k: x for k, x in v.items() if isinstance(x, str) and x >= bas.isoformat(timespec="seconds")}
    z = max(son.values()) if son else simdi.isoformat(timespec="seconds")
    if "metin_yok" in son or ("groq" in son and "gemini_metin" in son):
        return {"durum": "hata", "zaman": z, "mesaj": "Bugünkü ücretsiz metin kotası (Gemini + Groq yedeği) bitti; 11:00'de yenilenir, o saate kadar yeni metin yazılamayabilir"}
    if "gemini_ses" in son:
        return {"durum": "hata", "zaman": z, "mesaj": "Gemini'nin bugünkü ücretsiz seslendirme kotası doldu; 11:00'de yenilenir, kalan üretim sonraki çalışmada yapılır"}
    if "gemini_metin" in son:
        return {"durum": "tamam", "zaman": z, "mesaj": "Bazı Gemini modellerinin günlük kotası doldu; diğer modeller çalışıyor (11:00'de yenilenir)"}
    return {"durum": "tamam", "zaman": z, "mesaj": "Ücretsiz kota yeterli"}
