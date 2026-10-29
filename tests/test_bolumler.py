import json
import unittest
from pathlib import Path

from cocuk3d import bolum_denetle

SERI = Path(__file__).resolve().parent.parent / "seri" / "findik-ile-pamuk"


class BolumDenetimTesti(unittest.TestCase):
    def test_tum_bolumler_kurallara_uyar(self):
        self.assertEqual(bolum_denetle.seriyi_denetle(SERI), {})

    def test_uzaktaki_nesneyi_tutmak_yakalanir(self):
        seri = json.loads((SERI / "seri.json").read_text())
        b = json.loads((SERI / "bolumler" / "b001.json").read_text())
        b["nesne_yerlesim"] = {"palamut": [1.7, 0.5, 0.0]}
        self.assertTrue(any("çok uzakta" in h for h in bolum_denetle.denetle(b, seri)))

    def test_otururken_yurumek_yakalanir(self):
        seri = json.loads((SERI / "seri.json").read_text())
        b = json.loads((SERI / "bolumler" / "b001.json").read_text())
        k = next(iter(b["baslangic"]))
        b["cekimler"][0]["eylemler"] = [{"kim": k, "eylem": "otur", "bas": 0.0, "son": 0.2},
                                       {"kim": k, "eylem": "yuru", "bas": 0.3, "son": 0.6, "nereye": [0, 0]}]
        self.assertTrue(any("otururken" in h for h in bolum_denetle.denetle(b, seri)))


if __name__ == "__main__":
    unittest.main()
