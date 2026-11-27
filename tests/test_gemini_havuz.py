import os, tempfile
os.environ.setdefault("GEMINI_HAVUZ_DOSYASI", os.path.join(tempfile.mkdtemp(), "gemini-havuz.json"))  # testler otonom/ altına yazmasın
"""Gemini anahtar havuzu testleri (sahte HTTP; gerçek Gemini çağrısı YOK, kota harcanmaz)."""
import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    from ortak import gemini_havuz as H
except ImportError:  # paket içindeki kopya
    H = None

GUNLUK = json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "GIZLI_GOVDE", "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"}]}})
DAKIKA = json.dumps({"error": {"code": 429, "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}]}})
GECERSIZ = json.dumps({"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid.",
                                 "details": [{"reason": "API_KEY_INVALID"}]}})
TAMAM = json.dumps({"candidates": [{"content": {"parts": [{"text": "merhaba"}]}}]})


def modul():
    global H
    if H is None:
        H = _bul()
    return H


def _bul():
    import importlib
    for ad in ("gemini_havuz", "otopilot.gemini_havuz", "dc.gemini_havuz", "ortak.gemini_havuz", "hat.gemini_havuz"):
        try:
            return importlib.import_module(ad)
        except ImportError:
            continue
    raise ImportError("gemini_havuz bulunamadı")


class Sahte:
    """Anahtar → sıradaki yanıtlar. Her çağrıyı (model, parmak) olarak kaydeder."""

    def __init__(self, yanitlar):
        self.yanitlar = {k: list(v) for k, v in yanitlar.items()}
        self.cagrilar = []

    def __call__(self, model, govde, anahtar, zaman, yol="generateContent"):
        self.cagrilar.append((model, anahtar))
        sira = self.yanitlar.get(anahtar) or [(200, TAMAM)]
        y = sira.pop(0) if len(sira) > 1 else sira[0]
        if isinstance(y, BaseException):
            raise y
        return y


class HavuzTest(unittest.TestCase):
    def setUp(self):
        self.H = modul()
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.yol = self.d / "gemini-havuz.json"
        self.eski = os.environ.pop(self.H.DURUM_ORTAM, None)
        self.simdi = [dt.datetime(2026, 11, 28, 7, 30, tzinfo=dt.timezone.utc)]   # TR 10:30 → Pasifik 27 Kasım
        self.kayit = []
        self.uyku = []

    def tearDown(self):
        if self.eski is not None:
            os.environ[self.H.DURUM_ORTAM] = self.eski

    def havuz(self, sahte, ks=("A1", "B2", "C3")):
        return self.H.Havuz(self.yol, list(ks), gunluk=self.kayit.append, gonder=sahte,
                            uyku=self.uyku.append, saat=lambda: self.simdi[0])

    def test_anahtar_okuma_sira_ve_tekrar(self):
        ortam = {"GEMINI_API_KEY": "a", "GEMINI_API_KEY_3": "c", "GEMINI_API_KEY_2": " b ", "GEMINI_API_KEYS": "d, a,e"}
        env = self.d / ".env"
        env.write_text("GEMINI_API_KEY=a\nGEMINI_API_KEY_9='f'\n# GEMINI_API_KEY_4=x\nexport GEMINI_API_KEY_5=g\nGEMINI_API_KEY_6=\n")
        self.assertEqual(self.H.anahtarlar(ortam, env), ["a", "b", "c", "d", "e", "g", "f"])
        self.assertEqual(self.H.anahtarlar({}), [])

    def test_ilk_anahtar_gunluk_429_ikinciye_gecer_ve_kalici_isaretlenir(self):
        s = Sahte({"A1": [(429, GUNLUK)]})
        h = self.havuz(s)
        self.assertEqual(h.cagir("m-flash", {})["candidates"][0]["content"]["parts"][0]["text"], "merhaba")
        self.assertEqual(s.cagrilar, [("m-flash", "A1"), ("m-flash", "B2")])
        self.assertEqual(self.uyku, [], "günlük kotada beklenmez")
        v = json.loads(self.yol.read_text())
        self.assertEqual(v["gun"], "2026-11-27")
        self.assertIn(f"m-flash|{self.H.parmak('A1')}", v["dolu"])
        self.assertNotIn("A1", self.yol.read_text(), "anahtarın kendisi yazılmaz")
        self.assertTrue(any("günlük kota" in m and "quotaId=GenerateRequestsPerDay" in m for m in self.kayit))
        self.assertFalse(any("GIZLI_GOVDE" in m or "A1" in m for m in self.kayit), "gövde/anahtar loglanmaz")
        # yeni süreç (yeni Havuz nesnesi) aynı gün 1. anahtarı hiç denemez
        s2 = Sahte({})
        self.havuz(s2).cagir("m-flash", {})
        self.assertEqual(s2.cagrilar, [("m-flash", "B2")])
        # başka model (ör. TTS) ayrı kota: 1. anahtar o modelde denenir
        s3 = Sahte({})
        self.havuz(s3).cagir("m-tts", {})
        self.assertEqual(s3.cagrilar, [("m-tts", "A1")])

    def test_google_gunu_degisince_sifirlanir(self):
        h = self.havuz(Sahte({"A1": [(429, GUNLUK)]}))
        h.cagir("m", {})
        self.assertTrue(h.dolu_mu("m", "A1"))
        self.simdi[0] = dt.datetime(2026, 11, 28, 7, 59, tzinfo=dt.timezone.utc)   # TR 10:59: hâlâ aynı Google günü
        self.assertTrue(self.havuz(Sahte({})).dolu_mu("m", "A1"))
        self.simdi[0] = dt.datetime(2026, 11, 28, 8, 1, tzinfo=dt.timezone.utc)    # TR 11:01: yeni gün
        s = Sahte({})
        h2 = self.havuz(s)
        self.assertFalse(h2.dolu_mu("m", "A1"))
        h2.cagir("m", {})
        self.assertEqual(s.cagrilar, [("m", "A1")])
        self.assertEqual(json.loads(self.yol.read_text()), {"gun": "2026-11-28", "dolu": {}})

    def test_hepsi_doluysa_gunluk_kota_ve_bir_daha_istek_atilmaz(self):
        s = Sahte({k: [(429, GUNLUK)] for k in ("A1", "B2", "C3")})
        h = self.havuz(s)
        with self.assertRaises(self.H.GunlukKota):
            h.cagir("m", {})
        self.assertEqual(len(s.cagrilar), 3)
        with self.assertRaises(self.H.GunlukKota):
            h.cagir("m", {})
        self.assertEqual(len(s.cagrilar), 3, "dolu anahtarlara yeniden istek gitmez")
        self.assertTrue(h.hepsi_dolu("m"))

    def test_dakikalik_429_bekler_isaretlemez(self):
        s = Sahte({"A1": [(429, DAKIKA), (200, TAMAM)]})
        h = self.havuz(s)
        h.cagir("m", {}, deneme=3)
        self.assertEqual(s.cagrilar, [("m", "A1"), ("m", "A1")])
        self.assertEqual(self.uyku, [7.0])
        self.assertFalse(h.dolu_mu("m", "A1"))

    def test_dakikalik_sinir_surerse_sonrakine_gecer_isaretlemez(self):
        s = Sahte({"A1": [(429, DAKIKA)]})
        h = self.havuz(s)
        h.cagir("m", {}, deneme=2)
        self.assertEqual(s.cagrilar, [("m", "A1"), ("m", "A1"), ("m", "B2")])
        self.assertFalse(h.dolu_mu("m", "A1"))

    def test_hepsi_dakikalik_ise_gunluk_kota_denmez(self):
        s = Sahte({k: [(429, DAKIKA)] for k in ("A1", "B2")})
        with self.assertRaises(self.H.GeminiHatasi) as c:
            self.havuz(s, ("A1", "B2")).cagir("m", {}, deneme=1)
        self.assertNotIsInstance(c.exception, self.H.GunlukKota)
        self.assertEqual(c.exception.kod, 429)

    def test_503_kisa_bekler_ayni_anahtarla(self):
        s = Sahte({"A1": [(503, "{}"), (200, TAMAM)]})
        self.havuz(s).cagir("m", {})
        self.assertEqual(s.cagrilar, [("m", "A1"), ("m", "A1")])
        self.assertEqual(self.uyku, [5])

    def test_503_surerse_gecici_hata(self):
        s = Sahte({"A1": [(503, "{}")]})
        with self.assertRaises(self.H.GeminiHatasi) as c:
            self.havuz(s).cagir("m", {}, deneme=2)
        self.assertEqual(c.exception.kod, 503)

    def test_ag_hatasi_gecici(self):
        s = Sahte({"A1": [TimeoutError("x"), (200, TAMAM)]})
        self.havuz(s).cagir("m", {})
        self.assertEqual(len(s.cagrilar), 2)

    def test_gecersiz_anahtar_tum_modellerde_atlanir(self):
        s = Sahte({"A1": [(400, GECERSIZ)]})
        h = self.havuz(s)
        h.cagir("m1", {})
        self.assertEqual(s.cagrilar, [("m1", "A1"), ("m1", "B2")])
        s2 = Sahte({})
        self.havuz(s2).cagir("m2", {})
        self.assertEqual(s2.cagrilar, [("m2", "B2")])

    def test_404_hemen_hata_diger_anahtar_denenmez(self):
        s = Sahte({"A1": [(404, '{"error": {"status": "NOT_FOUND"}}')]})
        with self.assertRaises(self.H.GeminiHatasi) as c:
            self.havuz(s).cagir("m", {})
        self.assertEqual(c.exception.kod, 404)
        self.assertEqual(len(s.cagrilar), 1)

    def test_anahtar_yok(self):
        with self.assertRaises(self.H.AnahtarYok):
            self.havuz(Sahte({}), ()).cagir("m", {})

    def test_bozuk_durum_dosyasi_sifirlanir(self):
        self.yol.write_text("{bozuk")
        self.havuz(Sahte({})).cagir("m", {})
        self.assertEqual(json.loads(self.yol.read_text())["dolu"], {})

    def test_ozet_sir_icermez(self):
        h = self.havuz(Sahte({"A1": [(429, GUNLUK)]}))
        h.cagir("m", {})
        o = h.ozet()
        self.assertEqual(o["anahtar_sayisi"], 3)
        self.assertNotIn("A1", json.dumps(o))

    def test_ortam_degiskeni_durum_yolunu_ezer(self):
        ozel = self.d / "ozel.json"
        os.environ[self.H.DURUM_ORTAM] = str(ozel)
        try:
            self.havuz(Sahte({"A1": [(429, GUNLUK)]})).cagir("m", {})
        finally:
            os.environ.pop(self.H.DURUM_ORTAM)
        self.assertTrue(ozel.exists())
        self.assertFalse(self.yol.exists())

    def test_google_gunu(self):
        g = self.H.google_gunu
        self.assertEqual(g(dt.datetime(2026, 11, 28, 7, 59, tzinfo=dt.timezone.utc)), "2026-11-27")
        self.assertEqual(g(dt.datetime(2026, 11, 28, 8, 0, tzinfo=dt.timezone.utc)), "2026-11-28")


if __name__ == "__main__":
    unittest.main()
