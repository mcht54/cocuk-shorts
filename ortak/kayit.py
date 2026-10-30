"""İşin yazdığı JSON kayıt listesini depodaki en güncel listeyle birleştirir (aynı anda biten işler
birbirinin kaydını ezmesin). Kullanım: python -m ortak.kayit <depodaki_dosya> <işin_kopyası>
"""
import json
import sys
from pathlib import Path


def birlestir(depo_yolu, is_yolu):
    depo_yolu, is_yolu = Path(depo_yolu), Path(is_yolu)
    depo = json.loads(depo_yolu.read_text()) if depo_yolu.exists() else []
    gorulen = {json.dumps(k, sort_keys=True) for k in depo}
    yeni = json.loads(is_yolu.read_text()) if is_yolu.exists() else []
    depo += [k for k in yeni if json.dumps(k, sort_keys=True) not in gorulen]
    depo_yolu.write_text(json.dumps(depo, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    birlestir(*sys.argv[1:3])
