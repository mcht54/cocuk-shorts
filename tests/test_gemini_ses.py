"""Gemini ses kütüphanesi: ağ ve whisper SAHTE (kota harcanmaz)."""
import datetime as dt
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from cocuk3d import gemini_ses as G

AYAR = G.sesler({})


def _kel(metin, bas=0.06, adim=0.3):
    return [(round(bas + i * adim, 3), round(bas + i * adim + 0.25, 3), t) for i, t in enumerate(metin.split())]


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg yok")
class Kutuphane(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def _koy(self, kim, metin):
        sinyal = (0.2 * np.sin(np.arange(int(G.SR * (0.4 + 0.3 * len(metin.split())))) * 0.05)).astype(np.float32)
        G._yaz(self.d, kim, metin, sinyal, G._nokta(_kel(metin)), 0.95, AYAR)

    def test_tam_metin_ve_hepsi_ya_hic(self):
        self._koy("findik", "Merhaba Pamuk!")
        self.assertIsNotNone(G.al("findik", "Merhaba Pamuk!", AYAR, self.d))
        self.assertIsNone(G.al("pamuk", "Merhaba Pamuk!", AYAR, self.d))  # başka karakter başka ses
        self.assertIsNone(G.bolum_sesleri([("findik", "Merhaba Pamuk!"), ("pamuk", "Selam!")], AYAR, self.d))
        self._koy("pamuk", "Selam!")
        v = G.bolum_sesleri([("findik", "Merhaba Pamuk!"), ("pamuk", "Selam!")], AYAR, self.d)
        self.assertEqual(set(v), {("findik", "Merhaba Pamuk!"), ("pamuk", "Selam!")})
        sinyal, kel = v[("findik", "Merhaba Pamuk!")]
        self.assertEqual(sinyal.dtype, np.float32)
        self.assertEqual([k[2] for k in kel], ["Merhaba", "Pamuk!"])

    def test_uzun_derlemede_kesilen_satir(self):
        self._koy("findik", "Ceviz bulduk. Yarın devam!")
        v = G.al("findik", "Ceviz bulduk.", AYAR, self.d)
        self.assertIsNotNone(v)
        sinyal, kel = v
        self.assertEqual([k[2] for k in kel], ["Ceviz", "bulduk."])
        self.assertAlmostEqual(kel[0][0], 0.06, places=2)  # baş payı satır başında kırpılmaz
        self.assertLess(len(sinyal) / G.SR, 1.3)

    def test_bozuk_kutuphane_edgee_duser(self):
        (self.d / "dizin.json").write_text("{bozuk")
        self.assertIsNone(G.al("findik", "Yok böyle", AYAR, self.d))


class Pencere(unittest.TestCase):
    def test_saatler(self):
        tr = G.TR
        self.assertTrue(G.penceride(dt.datetime(2026, 11, 22, 23, 0, tzinfo=tr)))
        self.assertTrue(G.penceride(dt.datetime(2026, 11, 22, 4, 0, tzinfo=tr)))
        self.assertTrue(G.penceride(dt.datetime(2026, 11, 22, 10, 29, tzinfo=tr)))
        self.assertFalse(G.penceride(dt.datetime(2026, 11, 22, 10, 31, tzinfo=tr)))
        self.assertFalse(G.penceride(dt.datetime(2026, 11, 22, 16, 30, tzinfo=tr)))
        self.assertFalse(G.penceride(dt.datetime(2026, 11, 22, 21, 30, tzinfo=tr)))


class Butce(unittest.TestCase):
    def test_kota_429_hemen_durur(self):
        import io
        import urllib.error
        s = G.Sayac(5)
        hata = urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO(b'{"error": "PerDay"}'))
        with mock.patch.object(G, "_istek", side_effect=hata) as m, self.assertRaises(G.KotaBitti):
            s.cagir({})
        self.assertEqual(m.call_count, 1)

    def test_butce_biter(self):
        s = G.Sayac(0)
        with self.assertRaises(G.KotaBitti):
            s.cagir({})


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg yok")
class Hazirla(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def _sahte(self, duyulan):
        """_dinle sahtesi: her çağrıda sıradaki kelime listesini verir."""
        it = iter(duyulan)

        def dinle(sinyal):
            kel = next(it)
            return [types.SimpleNamespace(word=w, start=0.1 + i * 0.3, end=0.35 + i * 0.3) for i, w in enumerate(kel)]
        return dinle

    def test_ikili_cagri_bolunur_ve_yazilir(self):
        satirlar = [("findik", "Bak ceviz!"), ("pamuk", "Ne güzel!"), ("anlatici", "Orman uyandı.")]
        pcm = (np.zeros(G.SR * 3, dtype=np.int16) + 300).tobytes()
        sayac = G.Sayac(5)
        dinle = self._sahte([
            ["Bak", "ceviz!", "Ne", "güzel!"],  # ikili çağrı (bölme)
            ["Bak", "ceviz!"], ["Ne", "güzel!"],  # satır denetimi
            ["Orman", "uyandı."], ["Orman", "uyandı."],
        ])
        with mock.patch.object(G, "_istek", return_value={"candidates": [{"content": {"parts": [{"inlineData": {
                "data": __import__("base64").b64encode(pcm).decode()}}]}}]}) as m, \
                mock.patch.object(G, "_dinle", side_effect=dinle), mock.patch.object(G.time, "sleep"):
            self.assertTrue(G.hazirla(satirlar, AYAR, sayac, self.d))
        self.assertEqual(m.call_count, 2)  # Fındık+Pamuk tek çağrı, anlatıcı tek çağrı
        self.assertIsNotNone(G.bolum_sesleri(satirlar, AYAR, self.d))

    def test_tutmayan_satir_bolumu_eksik_birakir(self):
        satirlar = [("findik", "Bak ceviz!")]
        pcm = (np.zeros(G.SR, dtype=np.int16) + 300).tobytes()
        dinle = self._sahte([["Bak"], ["alakasız", "söz"], ["yine", "yanlış"], ["hiç", "değil"]])
        with mock.patch.object(G, "_istek", return_value={"candidates": [{"content": {"parts": [{"inlineData": {
                "data": __import__("base64").b64encode(pcm).decode()}}]}}]}), \
                mock.patch.object(G, "_dinle", side_effect=dinle), mock.patch.object(G.time, "sleep"):
            self.assertFalse(G.hazirla(satirlar, AYAR, G.Sayac(5), self.d))
        self.assertIsNone(G.bolum_sesleri(satirlar, AYAR, self.d))


class PlanlaBaglanti(unittest.TestCase):
    def test_turkce_satirlar_ingilizceyi_atlar(self):
        from cocuk3d import planla
        c = [{"satirlar": [{"kim": "findik", "metin": "Merhaba!"}, {"kim": "findik", "metin": "Hello!", "dil": "en"}]}]
        self.assertEqual(planla.turkce_satirlar(c), [("findik", "Merhaba!")])

    def test_hazirlik_uzun_giris_satirini_da_kapsar(self):
        import json
        from otonom import ses_hazirla
        seri = json.loads((ses_hazirla.SERI / "seri.json").read_text())
        b = json.loads(sorted((ses_hazirla.SERI / "bolumler").glob("b*.json"))[-1].read_text())
        s = ses_hazirla.bolum_satirlari(seri, b)
        self.assertTrue(any(k == "anlatici" and "Bölüm" in m for k, m in s))


if __name__ == "__main__":
    unittest.main()
