"""Bulut işinin yazdığı kayıtları depodaki en güncel kayıtla birleştirir (aynı anda biten
Shorts ve uzun video işleri birbirinin kaydını ezmesin).

Kullanım: python kayit_birlestir.py <işin yazdığı yayin_kaydi.json> <işin karakter_izleri.json>
Depodaki dosyalara (origin/main'e sıfırlanmış çalışma ağacı) işin yeni satırlarını ekler.
"""
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
KAYIT = KOK / "yayin_kaydi.json"
IZLER = KOK / "seri" / "findik-ile-pamuk" / "karakter_izleri.json"


def oku(yol, bos):
    yol = Path(yol)
    return json.loads(yol.read_text()) if yol.exists() else bos


def main(is_kaydi, is_izleri):
    depo = oku(KAYIT, [])
    gorulen = {json.dumps(k, sort_keys=True) for k in depo}
    depo += [k for k in oku(is_kaydi, []) if json.dumps(k, sort_keys=True) not in gorulen]
    KAYIT.write_text(json.dumps(depo, ensure_ascii=False, indent=1))
    izler = oku(IZLER, {})
    for ad, iz in oku(is_izleri, {}).items():
        izler.setdefault(ad, iz)  # kayıtlı parmak izi asla değiştirilmez
    IZLER.write_text(json.dumps(izler, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
