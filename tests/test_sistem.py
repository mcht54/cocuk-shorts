"""Birim testleri: python -m unittest discover tests
Ağ gerektiren uçtan uca test yalnız ENTEGRASYON=1 iken çalışır (edge-tts)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from cocuk import cizim, gorsel, kalite, video  # noqa: E402


class MuzikSes(unittest.TestCase):
    def test_muzik_tam_uzunlukta(self):
        # önceki hata: süre->örnek dönüşümünde 1 örnek eksik kalıyordu
        for n in (24000 * 30 + 1, 1013461, 811, 24000 * 41 + 23999):
            self.assertEqual(len(video.muzik(n, 7)), n)

    def test_karistir_uzunluk_farkinda_hata_verir(self):
        from array import array
        with self.assertRaises(ValueError):
            video.karistir(array("h", [0] * 100), array("f", [0.0] * 99))

    def test_karistir_kirpmaz(self):
        from array import array
        ses = array("h", [32000, -32000] * 2000)
        m = array("f", [1.0] * 4000)
        k = video.karistir(ses, m)
        self.assertEqual(len(k), 4000)
        self.assertLessEqual(max(abs(x) for x in k), 29000)


class Altyazi(unittest.TestCase):
    def _kelimeler(self):
        # "Merhaba minikler!" sonrası 1.1 sn duraklama (edge-tts'te ölçülen davranış)
        return [(0.10, 0.50, "Merhaba"), (0.50, 1.00, "minikler!"),
                (2.10, 2.40, "Bugün"), (2.40, 2.60, "sarı"), (2.60, 3.00, "rengi"),
                (3.00, 3.50, "öğreniyoruz."), (3.85, 4.20, "Hadi"), (4.20, 4.60, "söyle!")]

    def test_gruplar_cumle_sinirini_asmaz(self):
        for g in video.parcala(self._kelimeler()):
            for k in g[:-1]:
                self.assertNotIn(k[2][-1], ".!?", f"cümle sonu grubun ortasında: {g}")

    def test_duraklamada_altyazi_kaybolmaz(self):
        kel = self._kelimeler()
        gruplar = video.parcala(kel)
        cizelge = video.altyazi_zaman_cizelgesi(gruplar, 5.5)
        olcum = video.altyazi_olcum(kel, gruplar, cizelge)
        self.assertEqual(olcum["gosterilmeyen"], 0)
        self.assertLessEqual(olcum["en_uzun_bosluk_sn"], 0.2)

    def test_noktalama_geri_konur(self):
        kel = video._noktalama_koru("Vak vak! Bu ördek sarı",
                                    [(0, .1, "Vak"), (.1, .2, "vak"), (.3, .4, "Bu"),
                                     (.4, .5, "ördek"), (.5, .6, "sarı")])
        self.assertEqual([k[2] for k in kel], ["Vak", "vak!", "Bu", "ördek", "sarı."])


class YerelCizim(unittest.TestCase):
    def test_tum_emoji_dosyalari_var(self):
        eksik = [k for k in cizim.gerekli_kodlar() if not (cizim.EMOJI / f"emoji_u{k}.png").exists()]
        self.assertEqual(eksik, [])

    def test_her_ortam_kalite_kontrolunu_gecer(self):
        for ortam in cizim.ORTAMLAR:
            img, _ = cizim.sahne_ciz({"gorsel": "", "ortam": ortam}, None, 1)
            tamam, olcum, hatalar = gorsel.gorsel_kontrol(img)
            self.assertTrue(tamam, f"{ortam}: {hatalar} {olcum}")

    def test_ornek_senaryolarin_tum_sahneleri(self):
        for ad in ("masal", "egitici", "hayvan"):
            s = json.loads((KOK / "ornekler" / f"{ad}.json").read_text())
            k, o = cizim.ana_karakter(s), "cayir"
            for i, sahne in enumerate(s["sahneler"]):
                img, o = cizim.sahne_ciz(sahne, k, i, o)
                self.assertTrue(gorsel.gorsel_kontrol(img)[0], f"{ad} sahne {i}")

    def test_anahtar_kelime_eslesmeleri(self):
        self.assertNotIn("mavi", cizim.ogeleri_bul("a smiling sun in a blue sky"))
        self.assertEqual(cizim.ortam_bul("a little white bunny sitting under a tree, autumn forest"), "orman")
        self.assertEqual(cizim.ortam_bul("leaving a dark ink cloud", "deniz"), "deniz")
        self.assertNotIn("gunes", cizim.ogeleri_bul("a big yellow sunflower in a field"))
        self.assertNotIn("portakal", cizim.ogeleri_bul("a small orange squirrel"))

    def test_ana_karakter_tutarli(self):
        s = json.loads((KOK / "ornekler" / "masal.json").read_text())
        self.assertEqual(cizim.ana_karakter(s), "sincap")


class GorselKalite(unittest.TestCase):
    def test_duz_ve_degrade_reddedilir(self):
        self.assertFalse(gorsel.gorsel_kontrol(Image.new("RGB", (1080, 1920), (200, 220, 255)))[0])
        self.assertFalse(gorsel.gorsel_kontrol(cizim._degrade((255, 214, 165), (160, 196, 255)))[0])

    def test_anahtarsiz_yerel_cizime_duser(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            kota = gorsel.Kota(cf_sinir=4000)
            img, rapor, ortam = gorsel.sahne_gorseli(
                {"gorsel": "a fluffy yellow baby duck in a pond"}, "", None, 3, "cayir", kota)
        self.assertEqual(rapor["kaynak"], "yerel")
        self.assertEqual(ortam, "gol")

    def test_bozuk_ai_gorseli_reddedilir_ve_yerel_kullanilir(self):
        duz = Image.new("RGB", (1024, 1024), (128, 128, 128))
        with mock.patch.object(gorsel, "_cloudflare", return_value=duz):
            img, rapor, _ = gorsel.sahne_gorseli({"gorsel": "a cat"}, "", "kedi", 1, "oda",
                                                 gorsel.Kota(cf_sinir=4000))
        self.assertEqual(rapor["kaynak"], "yerel")
        self.assertTrue(any("kalite kontrolü reddetti" in n for n in rapor["notlar"]))

    def test_kota_hatasi_sonrasi_tekrar_denenmez(self):
        cevap = mock.Mock(ok=False, status_code=429, text="daily free allocation exceeded")
        env = {"CF_ACCOUNT_ID": "x", "CF_API_TOKEN": "y"}
        with mock.patch.dict(os.environ, env), mock.patch.object(gorsel.requests, "post",
                                                                 return_value=cevap) as post:
            kota = gorsel.Kota(cf_sinir=4000)
            for i in range(3):
                gorsel.sahne_gorseli({"gorsel": "a cat"}, "", "kedi", i, "oda", kota)
        self.assertEqual(post.call_count, 1)

    def test_gunluk_noron_siniri_cagri_yaptirmaz(self):
        env = {"CF_ACCOUNT_ID": "x", "CF_API_TOKEN": "y"}
        with mock.patch.dict(os.environ, env), mock.patch.object(gorsel.requests, "post") as post:
            kota = gorsel.Kota(cf_bugun=3990, cf_sinir=4000)
            _, rapor, _ = gorsel.sahne_gorseli({"gorsel": "a cat"}, "", "kedi", 1, "oda", kota)
        post.assert_not_called()
        self.assertEqual(rapor["kaynak"], "yerel")


class VideoKalite(unittest.TestCase):
    def _rapor(self, sure):
        return {"sure": sure, "ses_ornek": 1, "muzik_ornek": 1, "konusma_son": sure - 1,
                "sahne_baslari": [0.0, sure / 2], "gorseller": [],
                "altyazi": {"kelime": 10, "gosterilmeyen": 0, "en_uzun_bosluk_sn": 0}}

    def test_bozuk_dosya_reddedilir(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(os.urandom(5000))
            f.flush()
            tamam, hatalar, _ = kalite.denetle(f.name, self._rapor(20))
        self.assertFalse(tamam)

    def test_sessiz_ve_bos_video_reddedilir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "v.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=pink:s=1080x1920:d=20",
                            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "20",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(yol)], check=True)
            tamam, hatalar, _ = kalite.denetle(yol, self._rapor(20))
        self.assertFalse(tamam)
        metin = " ".join(hatalar)
        self.assertIn("ses çok kısık", metin)
        self.assertIn("boş/bozuk", metin)

    def test_yanlis_sure_reddedilir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "v.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:d=8",
                            "-f", "lavfi", "-i", "sine=f=440:r=24000:d=8",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(yol)], check=True)
            tamam, hatalar, _ = kalite.denetle(yol, self._rapor(20))
        self.assertFalse(tamam)
        self.assertTrue(any("süre" in h for h in hatalar))

    def test_eksik_altyazi_reddedilir(self):
        r = self._rapor(20)
        r["altyazi"] = {"kelime": 10, "gosterilmeyen": 2, "en_uzun_bosluk_sn": 1.4}
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            tamam, hatalar, _ = kalite.denetle(f.name, r)
        self.assertFalse(tamam)


class Calistirma(unittest.TestCase):
    def test_anahtar_yoksa_sahte_basari_yok(self):
        with tempfile.TemporaryDirectory() as d:
            gecmis = Path(d) / "gecmis.json"
            gecmis.write_text("[]")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("GEMINI", "CF_", "YT_"))}
            env.update(GECMIS_DOSYASI=str(gecmis), EN_FAZLA_DENEME="1")
            r = subprocess.run([sys.executable, str(KOK / "calistir.py"), "--tur", "masal"],
                               env=env, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(r.returncode, 0)
            kayit = json.loads(gecmis.read_text())[-1]
        self.assertEqual(kayit["durum"], "hata")
        self.assertIn("GEMINI_API_KEY", kayit["hata"])

    def test_kilitli_yayin_tekrar_yuklenmez(self):
        import calistir
        self.assertTrue(calistir.yayin_kilitli([{"durum": "yayinlandi"}, {"durum": "kilitli"}, {"durum": "hata"}]))
        self.assertFalse(calistir.yayin_kilitli([{"durum": "kilitli"}, {"durum": "yayinlandi"}]))


@unittest.skipUnless(os.environ.get("ENTEGRASYON") == "1", "ağ gerektirir (edge-tts)")
class UctanUca(unittest.TestCase):
    def test_ornek_senaryo_kaliteyi_gecer(self):
        s = json.loads((KOK / "ornekler" / "egitici.json").read_text())
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=False):
            for k in ("CF_ACCOUNT_ID", "CF_API_TOKEN"):
                os.environ.pop(k, None)
            mp4 = Path(d) / "v.mp4"
            rapor = video.uret(s, mp4, Path(d) / "is")
            tamam, hatalar, olcum = kalite.denetle(mp4, rapor)
        self.assertTrue(tamam, hatalar)
        self.assertEqual(rapor["ses_ornek"], rapor["muzik_ornek"])
        self.assertLess(abs(olcum["ses_sure"] - olcum["goruntu_sure"]), 0.1)


if __name__ == "__main__":
    unittest.main()
