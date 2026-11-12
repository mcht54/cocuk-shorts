import unittest

import bulut3d


class MetaTesti(unittest.TestCase):
    def test_bolum_adi_basa_genel_etiketler_once(self):
        m = bulut3d.meta_hazirla({"baslik": "Fındık ile Pamuk | Büyük Yarış | 3D Çocuk Çizgi Filmi",
                                  "etiketler": ["masal", "sincap"], "aciklama": "Yarış!"})
        self.assertEqual(m["baslik"], "Büyük Yarış | Fındık ile Pamuk | Çocuk Çizgi Filmi")
        self.assertEqual(m["etiketler"][0], "çizgi film")
        self.assertEqual(m["etiketler"].count("masal"), 1)
        self.assertIn("sincap", m["etiketler"])
        self.assertLessEqual(sum(len(e) + 2 for e in m["etiketler"]), 500)
        self.assertEqual(bulut3d.meta_hazirla(m)["aciklama"], m["aciklama"])  # iki kez eklenmez


if __name__ == "__main__":
    unittest.main()
