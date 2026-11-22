"""Derleme içeriği: mini dizi ortadan başlamaz; Uyku Öncesi derlemesine macera bölümü girmez; kapak bekleyenleri bulunur."""
import json
import unittest
from unittest import mock

import derleme
import kapak_tekrar


class Butunluk(unittest.TestCase):
    def test_mini_dizi_aralik_varsa_sonrakiler_cikar(self):
        p = [{"bolum": f"seri/findik-ile-pamuk/bolumler/{b}.json"} for b in ("b001", "b044", "b045", "b046")]  # Hazine Avı 3,4,5 (1-2 yok)
        kalan, neden = derleme.dizi_butunlugu(p)
        self.assertEqual([x["bolum"] for x in kalan], ["seri/findik-ile-pamuk/bolumler/b001.json"])
        self.assertEqual(len(neden), 3)

    def test_tam_mini_dizi_kalir(self):
        p = [{"bolum": f"seri/findik-ile-pamuk/bolumler/{b}.json"} for b in ("b042", "b043", "b044")]
        kalan, neden = derleme.dizi_butunlugu(p)
        self.assertEqual(len(kalan), 3)
        self.assertEqual(neden, [])

    def test_uyku_oncesi_macera_almaz(self):
        kayit = [{"profil": "shorts", "durum": "yuklendi", "bolum": f"seri/findik-ile-pamuk/bolumler/{b}.json"} for b in
                 ("b001", "b002", "b003", "b004", "b007", "b008", "b009", "b012", "b042", "b043", "b044")]
        with mock.patch.object(derleme, "kayitlar", return_value=kayit):
            secilen = derleme.sec_karisik()
        self.assertTrue(secilen)
        self.assertFalse(any(b.endswith(("b042.json", "b043.json", "b044.json")) for b in secilen))

    def test_kapak_bekleyenleri(self):
        vids, _ = kapak_tekrar.bekleyenler()
        self.assertIn("prRdKUPpw9k", vids)


if __name__ == "__main__":
    unittest.main()
