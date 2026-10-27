"""3D hattı testleri: python -m unittest discover -s tests
Blender gerektirenler ENTEGRASYON3D=1 ile çalışır (ağ gerektirmez)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from cocuk3d import animasyon, kalite3d, kamera, kurgu, planla, ses3d  # noqa: E402
from cocuk3d.profil import profil  # noqa: E402

SERI = KOK / "seri" / "findik-ile-pamuk"
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")


def _yuru_senaryosu():
    kar = {"a": {"konum": [-1, 0], "boy": 1.0, "tur": "tavsan"}, "b": {"konum": [1, 0], "boy": 1.0, "tur": "sincap"}}
    eylem = [{"kim": "a", "eylem": "yuru", "nereye": [0.5, 0], "bas": 0.2, "son": 1.8},
             {"kim": "a", "eylem": "tut", "nesne": "n", "bas": 1.8, "son": 2.3},
             {"kim": "a", "eylem": "ver", "nesne": "n", "kime": "b", "bas": 2.4, "son": 3.0},
             {"kim": "b", "eylem": "ifade", "tur": "uzgun", "bas": 0.0, "son": 0.01}]
    return kar, eylem


class Animasyon(unittest.TestCase):
    def test_yurume_konum_ve_bacak_hareketi(self):
        kar, eylem = _yuru_senaryosu()
        poz, tut = animasyon.hesapla(kar, eylem, 3.5, 24, {}, {"n": {"konum": [0, 0, 0]}})
        self.assertAlmostEqual(poz["a"][0]["konum"][0], -1.0, places=3)
        self.assertGreater(poz["a"][45]["konum"][0], 0.4)
        bacak = [p["kemik"]["bacak.L"][0] for p in poz["a"][5:43]]
        self.assertGreater(max(bacak) - min(bacak), 0.4, "yürürken bacaklar sallanmalı")

    def test_nesne_el_degistirir(self):
        kar, eylem = _yuru_senaryosu()
        _, tut = animasyon.hesapla(kar, eylem, 3.5, 24, {}, {"n": {"konum": [0, 0, 0]}})
        self.assertEqual(tut["n"][10], {})
        self.assertEqual(tut["n"][int(2.2 * 24)], {"a": 1.0})
        self.assertEqual(tut["n"][int(3.2 * 24)], {"b": 1.0})

    def test_bosta_bile_hareket_var_ve_goz_kirpar(self):
        kar = {"a": {"konum": [0, 0], "boy": 1, "tur": "tavsan"}}
        poz, _ = animasyon.hesapla(kar, [], 6.0, 24, {}, {})
        nefes = [p["olcek"]["govde"][2] for p in poz["a"]]
        goz = [p["olcek"]["goz.L"][2] for p in poz["a"]]
        self.assertGreater(max(nefes) - min(nefes), 0.02)
        self.assertLess(min(goz), 0.2, "6 sn içinde en az bir göz kırpma")

    def test_tekrarlanabilir(self):
        kar, eylem = _yuru_senaryosu()
        a = animasyon.hesapla(kar, eylem, 3.5, 24, {}, {"n": {"konum": [0, 0, 0]}})
        b = subprocess.run([sys.executable, "-c", (
            "import sys,json; sys.path.insert(0, %r); from tests.test_3d import _yuru_senaryosu;"
            "from cocuk3d import animasyon; k,e=_yuru_senaryosu();"
            "print(json.dumps(animasyon.hesapla(k,e,3.5,24,{},{'n':{'konum':[0,0,0]}})[0]['a'][77]))") % str(KOK)],
            capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": "123"})
        self.assertEqual(json.loads(b.stdout), json.loads(json.dumps(a[0]["a"][77])),
                         "farklı süreçte aynı poz (hash tohumundan bağımsız)")

    def test_konusma_agzi_acar(self):
        kar = {"a": {"konum": [0, 0], "boy": 1, "tur": "tavsan"}}
        zarf = [0.0] * 24 + [1.0] * 24
        poz, _ = animasyon.hesapla(kar, [], 2.0, 24, {"a": zarf}, {})
        self.assertGreater(poz["a"][36]["olcek"]["agiz"][2], 2 * poz["a"][10]["olcek"]["agiz"][2])

    def test_agiz_asiri_acilmaz(self):
        # önceki hata: şaşkın ifade × tam konuşma ağzı 7.9× uzatıyordu ("sarkan dil")
        kar = {"a": {"konum": [0, 0], "boy": 1, "tur": "sincap"}}
        e = [{"kim": "a", "eylem": "ifade", "tur": "saskin", "bas": 0.0, "son": 0.01}]
        poz, _ = animasyon.hesapla(kar, e, 2.0, 24, {"a": [1.0] * 48}, {})
        self.assertLessEqual(max(p["olcek"]["agiz"][2] for p in poz["a"]), animasyon.AGIZ_EN_COK)


class Kamera(unittest.TestCase):
    def test_dikey_kadraj_daha_uzak(self):
        d_dikey = kamera.cerceve_uzakligi("iki_kisi", 2.0, 1.2, 1080, 1920)
        d_yatay = kamera.cerceve_uzakligi("iki_kisi", 2.0, 1.2, 1920, 1080)
        self.assertGreater(d_dikey, d_yatay)

    def test_yaklas_kamerayi_hareket_ettirir(self):
        poz = {"a": [{"konum": [0, 0, 0], "yon": 0.0}] * 48}
        yol = kamera.kamera_yolu({"tip": "orta", "hareket": "yaklas", "hedef": ["a"]}, poz, {"a": 1}, 0, 48, 1080, 1920)
        self.assertGreater(np.linalg.norm(np.array(yol[0]["konum"]) - np.array(yol[-1]["konum"])), 0.2)

    def test_isik_gecisi(self):
        y = kamera.isik_yolu({"isik": "sabah", "isik_son": "aksam"}, 20)
        self.assertNotEqual(y[0]["gunes"], y[-1]["gunes"])


class Ses(unittest.TestCase):
    def test_muzik_konusmayi_bastirmaz(self):
        n = ses3d.SR * 4
        t = np.arange(n) / ses3d.SR
        konusma = np.where((t > 1) & (t < 3), 0.3 * np.sin(2 * np.pi * 220 * t), 0).astype(np.float32)
        maske = (t > 1) & (t < 3)
        karisim, muzik_son = ses3d.karistir(konusma, ses3d.muzik(n, 1), np.zeros(n, np.float32), maske)
        self.assertGreaterEqual(ses3d.konusma_muzik_farki_db(konusma, muzik_son, maske), 10)
        self.assertLessEqual(np.max(np.abs(karisim)), 0.891)

    def test_efektler_uretilir(self):
        for tur in ("zipla", "adim", "pop", "parilti"):
            self.assertGreater(np.max(np.abs(ses3d.efekt(tur))), 0.01)


class Planlama(unittest.TestCase):
    def test_tanimsiz_karakter_reddedilir(self):
        b = json.loads((SERI / "bolumler" / "b001.json").read_text())
        b["cekimler"][0]["satirlar"][0]["kim"] = "yeni_kahraman"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(b, f)
        with self.assertRaises(ValueError):
            planla.yukle(SERI, f.name)

    def test_profiller(self):
        self.assertGreater(profil("shorts")["boy"], profil("shorts")["en"])
        self.assertGreater(profil("uzun")["en"], profil("uzun")["boy"])
        self.assertEqual(profil("uzun")["sure"][0], 60.0)
        self.assertTrue(profil("uzun", prototip=True)["prototip"])


class Altyazi(unittest.TestCase):
    def test_gruplar_konusmaci_karistirmaz(self):
        k = [{"bas": 0.1, "son": 0.4, "metin": "Merhaba", "kim": "findik"},
             {"bas": 0.4, "son": 0.7, "metin": "Pamuk!", "kim": "findik"},
             {"bas": 0.75, "son": 1.0, "metin": "Selam", "kim": "pamuk"}]
        for g in kurgu.gruplar_olustur(k):
            self.assertEqual(len({w[3] for w in g}), 1)


class YayinGuvenligi(unittest.TestCase):
    def test_onaysiz_herkese_acik_yukleme_yok(self):
        from cocuk import youtube
        with mock.patch.object(youtube.requests, "post") as post, mock.patch.object(youtube.requests, "put") as put:
            for g in ("public", "unlisted"):
                with self.assertRaises(youtube.OnaySiz):
                    youtube.yukle(__file__, {"baslik": "x"}, "anahtar", gizlilik=g)
        post.assert_not_called()
        put.assert_not_called()

    def test_varsayilan_private_acikca_gonderilir(self):
        from cocuk import youtube
        cevap = mock.Mock(headers={"Location": "u"}, raise_for_status=lambda: None)
        bitti = mock.Mock(raise_for_status=lambda: None,
                          json=lambda: {"id": "v1", "status": {"privacyStatus": "private"}})
        with mock.patch.object(youtube.requests, "post", return_value=cevap) as post, \
                mock.patch.object(youtube.requests, "put", return_value=bitti):
            vid, durum = youtube.yukle(__file__, {"baslik": "x"}, "anahtar")
        self.assertEqual(post.call_args.kwargs["json"]["status"]["privacyStatus"], "private")
        self.assertEqual(post.call_args.kwargs["json"]["status"]["selfDeclaredMadeForKids"], True)
        self.assertEqual(durum["privacyStatus"], "private")

    def test_yayinla3d_onizleme_ve_kalmis_videoyu_reddeder(self):
        import yayinla3d
        with tempfile.TemporaryDirectory() as d:
            mp4 = Path(d) / "v.mp4"
            mp4.write_bytes(b"x" * 100)
            mp4.with_suffix(".rapor.json").write_text(json.dumps(
                {"kalite_gecti": False, "onizleme": True, "bolum": "b", "profil": "shorts"}))
            _, sorun = yayinla3d.denetle(mp4, [])
            self.assertEqual(len(sorun), 2)
            mp4.with_suffix(".rapor.json").write_text(json.dumps(
                {"kalite_gecti": True, "onizleme": False, "bolum": "b", "profil": "shorts"}))
            _, sorun = yayinla3d.denetle(mp4, [{"sha": yayinla3d.sha(mp4), "bolum": "x", "profil": "uzun",
                                                "video_id": "v"}])
            self.assertTrue(any("zaten yüklendi" in s for s in sorun), "çift yayın engellenmeli")

    def test_ucretli_servis_varsayilan_kapali(self):
        from cocuk import gorsel
        with mock.patch.dict(os.environ, {}, clear=True):
            k = gorsel.Kota()
        self.assertLessEqual(k.cf_sinir, 10000 * 0.5, "Cloudflare günlük ücretsiz kotanın yarısını aşmamalı")
        self.assertTrue(k.pol_kapali)


class Kuyruk(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["KUYRUK_DOSYASI"] = str(Path(self.d) / "k.json")
        import importlib

        import kuyruk
        self.k = importlib.reload(kuyruk)

    def tearDown(self):
        os.environ.pop("KUYRUK_DOSYASI", None)
        shutil.rmtree(self.d)

    def test_cift_is_eklenmez(self):
        k = self.k.oku()
        b = str(SERI / "bolumler" / "b001.json")
        self.assertIsNotNone(self.k.ekle(k, b, "shorts", False))
        self.assertIsNone(self.k.ekle(k, b, "shorts", False))
        self.assertIsNotNone(self.k.ekle(k, b, "uzun", True))

    def test_onizleme_sonra_tam_sonra_gecti(self):
        k = self.k.oku()
        self.k.ekle(k, str(SERI / "bolumler" / "b001.json"), "shorts", False)
        i = self.k.calistir_bir(k, lambda c: ["true"])
        self.assertEqual((i["asama"], i["durum"]), ("tam", "bekliyor"))
        i = self.k.calistir_bir(k, lambda c: ["true"])
        self.assertEqual(i["durum"], "gecti")

    def test_hata_sinirli_yeniden_denenir(self):
        k = self.k.oku()
        self.k.ekle(k, str(SERI / "bolumler" / "b001.json"), "shorts", False)
        self.assertEqual(self.k.calistir_bir(k, lambda c: ["false"])["durum"], "yeniden_dene")
        self.assertEqual(self.k.calistir_bir(k, lambda c: ["false"])["durum"], "hata")
        self.assertIsNone(self.k.calistir_bir(k, lambda c: ["true"]), "hatalı iş tekrar çalışmaz")


def _onizleme_dizini():
    """Güncel kalite kontrolünü geçmiş en yeni 3D videoyu ve KENDİ ölçüm verisini bulur."""
    for r_yol in sorted((KOK / "cikti3d" / "findik-ile-pamuk").glob("b001-*.rapor.json"), reverse=True):
        r = json.loads(r_yol.read_text())
        veri = KOK / r["veri"] if r.get("veri") else None
        if r.get("kalite_gecti") and veri and veri.exists():
            return veri, KOK / r["video"]
    return None, None


class BozukVideo(unittest.TestCase):
    """Gerçek, kaliteyi geçmiş bir 3D önizlemeyi bozup kontrolün yakaladığını doğrular."""

    @classmethod
    def setUpClass(cls):
        veri, cls.mp4 = _onizleme_dizini()
        if not cls.mp4:
            raise unittest.SkipTest("önce kaliteyi geçmiş bir 3D video üretilmeli (uret3d.py)")
        cls.tmp = Path(tempfile.mkdtemp())
        cls.veri = veri
        # bozuk kopyalar SHA'dan değil gerçek ses/görüntü kontrollerinden kalmalı: imzasız veri kopyası
        cls.is_dizini = cls.tmp / "veri"
        cls.is_dizini.mkdir()
        for f in ("meta.json", "kurgu.json", "altyazi.json"):
            shutil.copy2(veri / f, cls.is_dizini / f)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _bozuk(self, ad, *ffmpeg_arg):
        cikti = self.tmp / f"{ad}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.mp4), *ffmpeg_arg, str(cikti)], check=True)
        return kalite3d.denetle(cikti, self.is_dizini, SERI)

    def test_saglam_video_gecer(self):
        tamam, hatalar, _ = kalite3d.denetle(self.mp4, self.veri, SERI)  # imzalı, kendi verisiyle
        self.assertTrue(tamam, hatalar)

    def test_baska_videonun_verisi_reddedilir(self):
        kopya = self.tmp / "baska.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.mp4), "-c", "copy",
                        "-metadata", "comment=x", str(kopya)], check=True)
        tamam, h, _ = kalite3d.denetle(kopya, self.veri, SERI)
        self.assertFalse(tamam)
        self.assertIn("ait değil", h[0])

    def test_sessiz_video_kalir(self):
        tamam, h, _ = self._bozuk("sessiz", "-af", "volume=0", "-c:v", "copy")
        self.assertFalse(tamam)
        self.assertTrue(any("ses" in x for x in h), h)

    def test_siyah_kareli_video_kalir(self):
        tamam, h, _ = self._bozuk("siyah", "-vf", "drawbox=enable='between(t,5,6)':color=black:t=fill",
                                  "-c:a", "copy")
        self.assertFalse(tamam)
        self.assertTrue(any("siyah" in x for x in h), h)

    def test_donmus_video_kalir(self):
        n = json.loads((self.is_dizini / "kurgu.json").read_text())["kare_say"]
        tamam, h, _ = self._bozuk("donuk", "-vf", f"loop=loop=60:size=1:start=100,trim=end_frame={n},setpts=N/24/TB",
                                  "-c:a", "copy")
        self.assertFalse(tamam)
        self.assertTrue(any("donuk" in x for x in h), h)

    def test_kisaltilmis_video_kalir(self):
        tamam, h, _ = self._bozuk("kisa", "-t", "20", "-c", "copy")
        self.assertFalse(tamam)

    def test_kaymis_ses_dudak_senkronunu_bozar(self):
        tamam, h, _ = self._bozuk("kayik", "-af", "adelay=400", "-c:v", "copy")
        self.assertFalse(tamam)


@unittest.skipUnless(os.environ.get("ENTEGRASYON3D") == "1", "Blender gerektirir")
class Blender3D(unittest.TestCase):
    """İnternetsiz: diyalogsuz test bölümü, iki farklı mekânda aynı karakter."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.sonuc = {}
        for mekan, prof in (("orman", "shorts"), ("oda", "uzun")):
            d = cls.tmp / mekan
            with mock.patch.object(ses3d, "satir_seslendir", side_effect=AssertionError("ağ çağrısı!")):
                planla.planla(SERI, KOK / "tests" / "veri" / f"test_{mekan}.json", prof, d, prototip=True)
            r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(KOK / "cocuk3d" / "blender_sahne.py"),
                                "--", "kur", str(d / "plan.json"), str(d), "4", "20"], capture_output=True, text=True, timeout=600)
            assert "KURULUM_TAMAM" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
            subprocess.run([BLENDER, "-b", "-P", str(KOK / "cocuk3d" / "blender_sahne.py"), "--", "render", str(d), "30", "30"],
                           capture_output=True, timeout=600, check=True)
            cls.sonuc[mekan] = (d, json.loads((d / "meta.json").read_text()), json.loads((d / "plan.json").read_text()))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_1_ayni_karakter_iki_sahnede_ayni_gorunus(self):
        a = self.sonuc["orman"][1]["parmak_izi"]["pamuk"]
        b = self.sonuc["oda"][1]["parmak_izi"]["pamuk"]
        self.assertEqual(a, b)
        kayit = json.loads((SERI / "karakter_izleri.json").read_text()) if (SERI / "karakter_izleri.json").exists() else {}
        if "pamuk" in kayit:
            self.assertEqual(a, kayit["pamuk"], "seri kaydıyla aynı model")

    def test_2_karakter_gercekten_hareket_ediyor(self):
        km = self.sonuc["orman"][1]["kareler"]
        yol = np.linalg.norm(np.array(km[50]["karakter"]["pamuk"]["konum"][:2]) - np.array(km[2]["karakter"]["pamuk"]["konum"][:2]))
        self.assertGreater(yol, 0.5)
        ayak = [k["karakter"]["pamuk"]["ayak.L"][1] - k["karakter"]["pamuk"]["konum"][1] for k in km[5:50]]
        self.assertGreater(max(ayak) - min(ayak), 0.03, "ayak gövdeye göre ileri-geri gitmeli")

    def test_3_kamera_ve_isik_degisiyor(self):
        km = self.sonuc["orman"][1]["kareler"]
        self.assertGreater(np.linalg.norm(np.array(km[0]["kamera"][:3]) - np.array(km[55]["kamera"][:3])), 0.1)
        self.assertGreater(abs(km[0]["gunes"] - km[59]["gunes"]), 0.3)

    def test_4_dikey_ve_yatay_render(self):
        from PIL import Image
        dikey = Image.open(self.sonuc["orman"][0] / "kareler" / "k_0030.png")
        yatay = Image.open(self.sonuc["oda"][0] / "kareler" / "k_0030.png")
        self.assertGreater(dikey.height, dikey.width)
        self.assertGreater(yatay.width, yatay.height)
        for img in (dikey, yatay):
            self.assertGreater(np.asarray(img.convert("L")).std(), 15, "boş/siyah olmayan gerçek render")


if __name__ == "__main__":
    unittest.main()
