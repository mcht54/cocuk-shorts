"""Alt çekimler (konuşana yakın plan, ara açı) ve kısa yürüyüş işareti."""
import unittest

from cocuk3d import planla

FPS = 24


def _cekim(sure, eylemler=(), tip="iki_kisi", hedef=("findik", "pamuk"), **k):
    c = {"id": "c1", "tip": tip, "hareket": "sabit", "hedef": list(hedef), "bas": 10.0, "sure": sure,
         "bas_kare": 240, "kare_say": int(sure * FPS), "isik": "sabah", "eylemler": list(eylemler)}
    c.update(k)
    return c


def _satir(kim, bas):
    return {"kim": kim, "bas": bas, "cekim": "c1"}


class AltCekim(unittest.TestCase):
    def _denetle(self, alt, c):
        self.assertEqual(alt[0]["bas_kare"], c["bas_kare"])
        self.assertEqual(sum(a["kare_say"] for a in alt), c["kare_say"])  # kare kaybı/çakışma yok
        for a, b in zip(alt, alt[1:]):
            self.assertEqual(a["bas_kare"] + a["kare_say"], b["bas_kare"])
            self.assertFalse(a["tip"] == b["tip"] and a.get("hedef") == b.get("hedef") and a.get("taraf") == b.get("taraf"),
                             "art arda aynı açı")
        self.assertEqual(len({a["id"] for a in alt}), len(alt))

    def test_konusana_yakin_plan_ve_en_uzun_tek_aci(self):
        c = _cekim(10.0)
        alt = planla.alt_cekimler(c, [_satir("findik", 10.2), _satir("pamuk", 13.0), _satir("findik", 16.5)], FPS)
        self._denetle(alt, c)
        self.assertGreaterEqual(len(alt), 3)
        self.assertIn(("yakin", ["pamuk"]), [(a["tip"], a["hedef"]) for a in alt])
        self.assertLessEqual(max(a["kare_say"] for a in alt) / FPS, planla.KESME_EN_UZUN + 0.05)
        self.assertGreaterEqual(min(a["kare_say"] for a in alt) / FPS, planla.KESME_EN_KISA - 0.05)

    def test_kisa_ya_da_isik_gecisli_cekime_dokunulmaz(self):
        self.assertEqual(len(planla.alt_cekimler(_cekim(3.0), [_satir("pamuk", 11.5)], FPS)), 1)
        self.assertEqual(len(planla.alt_cekimler(_cekim(10.0, isik_son="aksam"), [_satir("pamuk", 13)], FPS)), 1)
        self.assertEqual(len(planla.alt_cekimler(_cekim(10.0), [_satir("pamuk", 13)], FPS, kesme=False)), 1)

    def test_yuruyus_ortasinda_kesme_yok_ve_eylem_parcasinda_kalir(self):
        c = _cekim(10.0, [{"kim": "findik", "eylem": "yuru", "bas": 0.1, "son": 0.9, "nereye": [1, 0]}])
        alt = planla.alt_cekimler(c, [_satir("pamuk", 13.0), _satir("findik", 16.0)], FPS)
        self.assertEqual(len(alt), 1)
        self.assertEqual([e["eylem"] for e in alt[0]["eylemler"]], ["yuru"])

    def test_uzun_el_sallama_gorundukten_sonra_kesilir(self):
        c = _cekim(10.0, [{"kim": "findik", "eylem": "el_salla", "bas": 0.0, "son": 0.95}])
        alt = planla.alt_cekimler(c, [], FPS)
        self._denetle(alt, c)
        self.assertGreater(len(alt), 1)
        self.assertEqual([e["eylem"] for e in alt[0]["eylemler"]], ["el_salla"])  # ölçüm, başladığı parçada
        self.assertGreaterEqual(alt[0]["kare_say"] / FPS, planla.KESME_EN_KISA)


class KisaYuruyus(unittest.TestCase):
    def test_on_santimlik_yuru_isaretlenir_gercek_yuruyus_degil(self):
        b = {"baslangic": {"findik": [-0.5, 0.2], "pamuk": [0.5, 0.2]}}
        c = [{"eylemler": [{"kim": "findik", "eylem": "yuru", "bas": 0.0, "nereye": [-0.4, 0.25]},
                           {"kim": "pamuk", "eylem": "yuru", "bas": 0.1, "nereye": [-0.5, 0.2]}]}]
        planla._kisa_yuruyusleri_isaretle(c, b, 1.0)
        self.assertTrue(c[0]["eylemler"][0].get("_kisa"))
        self.assertFalse(c[0]["eylemler"][1].get("_kisa"))


if __name__ == "__main__":
    unittest.main()
