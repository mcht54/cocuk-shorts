import unittest

import bulut3d


class MetaTesti(unittest.TestCase):
    def test_bolum_adi_basa_genel_etiketler_sonra(self):
        bolum = {"baslik": "Büyük Yarış", "deger": "azim", "bolum_no": 9,
                 "youtube": {"baslik": "Fındık ile Pamuk | Büyük Yarış | 3D Çocuk Çizgi Filmi",
                             "etiketler": ["masal", "sincap"], "aciklama": "Yarış! Bu bölümün değeri: azim."}}
        m, sorun = bulut3d.meta_hazirla(bolum)
        self.assertEqual(sorun, [])
        self.assertEqual(m["baslik"], "Büyük Yarış | Fındık ile Pamuk | Çocuk Çizgi Filmi")
        self.assertEqual(m["etiketler"][0], "Büyük Yarış")
        self.assertEqual([e.lower() for e in m["etiketler"]].count("masal"), 1)
        self.assertIn("sincap", m["etiketler"])
        self.assertLessEqual(sum(len(e) + 2 for e in m["etiketler"]), 500)
        self.assertEqual(m["aciklama"].count("azim"), 1)  # "Bu bölümün değeri" iki kez yazılmaz
        self.assertTrue(m["aciklama"].startswith("Büyük Yarış — Fındık ile Pamuk çizgi film masalı."))


if __name__ == "__main__":
    unittest.main()
