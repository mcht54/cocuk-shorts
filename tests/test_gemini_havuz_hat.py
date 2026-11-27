"""Çocuk Shorts ↔ Gemini anahtar havuzu (sahte HTTP; gerçek çağrı yok, kota harcanmaz)."""
import base64
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

os.environ.setdefault("GEMINI_HAVUZ_DOSYASI", os.path.join(tempfile.mkdtemp(), "gemini-havuz.json"))  # otonom/ kirlenmesin

from cocuk3d import gemini_ses as G  # noqa: E402
from ortak import gemini as OG  # noqa: E402

GUNLUK = json.dumps({"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                                         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}})
SES = {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(b"\x01\x00").decode()}}]}}]}


class Ortam(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.yama = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "bir", "GEMINI_API_KEY_2": "iki",
                                                 "GEMINI_HAVUZ_DOSYASI": os.path.join(self.d, "h.json")})
        self.yama.start()

    def tearDown(self):
        self.yama.stop()


class SesHavuz(Ortam):
    def test_birinci_anahtar_dolu_ikinciyle_ses(self):
        cagri = []

        def istek(govde, zaman=180, anahtar=None):
            cagri.append(anahtar)
            if anahtar == "bir":
                raise urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO(GUNLUK.encode()))
            return SES
        with mock.patch.object(G, "_istek", side_effect=istek):
            s = G.Sayac(5)
            self.assertEqual(s.cagir({}), b"\x01\x00")
            self.assertEqual(cagri, ["bir", "iki"])
            G.Sayac(5).cagir({})
            self.assertEqual(cagri, ["bir", "iki", "iki"], "dolu anahtar aynı Google gününde denenmez")
        self.assertEqual(s.kalan, 3)

    def test_hepsi_doluysa_kota_bitti(self):
        def istek(govde, zaman=180, anahtar=None):
            raise urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO(GUNLUK.encode()))
        with mock.patch.object(G, "_istek", side_effect=istek) as m, self.assertRaises(G.KotaBitti):
            G.Sayac(5).cagir({})
        self.assertEqual(m.call_count, 2)


class MetinHavuz(Ortam):
    def test_sor_ikinci_anahtara_gecer(self):
        cagri = []

        class Y:
            def __init__(self, kod, metin):
                self.status_code, self.text = kod, metin

        def post(url, headers=None, json=None, timeout=None):
            cagri.append(headers["x-goog-api-key"])
            if headers["x-goog-api-key"] == "bir":
                return Y(429, GUNLUK)
            return Y(200, '{"candidates": [{"content": {"parts": [{"text": "{\\"a\\": 1}"}]}}]}')
        with mock.patch.object(OG.requests, "post", side_effect=post), mock.patch.object(OG, "ARA_BEKLEME", 0), \
                mock.patch.object(OG, "_kota"):
            self.assertEqual(OG.sor("x"), {"a": 1})
        self.assertEqual(cagri, ["bir", "iki"])


if __name__ == "__main__":
    unittest.main()
