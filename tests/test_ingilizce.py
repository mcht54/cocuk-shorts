"""İngilizce ders hattı (2026-11-13): takvim, hat seçimi, ders denetimi, SEO bilgisi, derleme ayrımı."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import bulut3d
import derleme
from cocuk3d import bolum_denetle
from otonom import ingilizce_yaz, seo, takvim

DEPO = Path(__file__).resolve().parent.parent
SERI = DEPO / "seri" / "findik-ile-pamuk"
E = "seri/findik-ile-pamuk/bolumler/e{:03d}.json"
B = "seri/findik-ile-pamuk/bolumler/b{:03d}.json"


def ders(no):
    return json.loads((DEPO / E.format(no)).read_text())


class Takvim(unittest.TestCase):
    def test_hatlar_birbirinin_saatini_doldurmaz(self):
        simdi = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
        self.assertEqual(len(takvim.bos_slotlar("ingilizce_shorts", [], simdi)), 7)
        slot = takvim.bos_slotlar("ingilizce_shorts", [], simdi)[0]
        masal = [{"bolum": B.format(1), "profil": "shorts", "durum": "yuklendi", "yayin_zamani": slot.isoformat()}]
        self.assertEqual(len(takvim.bos_slotlar("ingilizce_shorts", masal, simdi)), 7)
        ing = [{"bolum": E.format(1), "profil": "shorts", "durum": "yuklendi", "yayin_zamani": slot.isoformat()}]
        self.assertEqual(len(takvim.bos_slotlar("ingilizce_shorts", ing, simdi)), 6)
        self.assertEqual(len(takvim.bos_slotlar("masal_shorts", ing, simdi)), 7)

    def test_eski_kayit_hatti_dosyadan(self):
        self.assertEqual(takvim.kayit_hatti({"profil": "shorts", "bolum": B.format(3)}), "masal_shorts")
        self.assertEqual(takvim.kayit_hatti({"profil": "shorts", "bolum": E.format(3)}), "ingilizce_shorts")


class HatSecimi(unittest.TestCase):
    def test_en_yakin_bos_saat_ve_dogru_bolum_dosyalari(self):
        with mock.patch.dict(os.environ, {"YAYIN": "acik", "HAT": "", "BOLUM": ""}):
            sira, bos = bulut3d.sira_ve_slotlar([], "ingilizce_shorts")
            self.assertTrue(sira and all(p.name.startswith("e") for p in sira))
            sira_m, bos_m = bulut3d.sira_ve_slotlar([], "masal_shorts")
            self.assertTrue(all(p.name.startswith("b") for p in sira_m))
            beklenen = "ingilizce_shorts" if bos[0] < bos_m[0] else "masal_shorts"
            self.assertEqual(bulut3d.hat_sec([]), beklenen)
        self.assertEqual(bulut3d.bolum_hatti(E.format(2)), "ingilizce_shorts")
        self.assertEqual(bulut3d.bolum_hatti(B.format(2)), "masal_shorts")


class DersDenetimi(unittest.TestCase):
    def test_elle_yazilan_dersler_gecer(self):
        seri = json.loads((SERI / "seri.json").read_text())
        for no in range(1, 5):
            b = ders(no)
            self.assertEqual(bolum_denetle.denetle(b, seri), [], no)
            self.assertEqual(ingilizce_yaz.ders_denetle(b), [], no)
            self.assertLessEqual(bolum_denetle.tahmini_sure(b), 50, no)

    def test_ingilizce_satirda_turkce_yakalanir(self):
        h = bolum_denetle.ingilizce_satir_denetle("c1", {"kim": "findik", "dil": "en", "metin": "Hello, Fındık!"})
        self.assertTrue(h)
        h = bolum_denetle.ingilizce_satir_denetle("c1", {"kim": "findik", "metin": "Merhaba!", "anlam": "x"})
        self.assertTrue(h)

    def test_tekrarsiz_ve_turkce_satirda_hedef_kelime(self):
        b = ders(4)
        b["cekimler"][1]["satirlar"] = [b["cekimler"][1]["satirlar"][0]]  # "Apple!" tekrarı silindi
        b["cekimler"][4]["satirlar"][0]["metin"] = "Ball! Bucket!"
        b["cekimler"][2]["satirlar"][1]["metin"] = "Ball demek. Hadi söyle!"
        h = ingilizce_yaz.ders_denetle(b)
        self.assertTrue(any("'apple' en az 2" in x for x in h))
        self.assertTrue(any("Türkçe satırda İngilizce hedef kelime var ('ball')" in x for x in h))

    def test_mufredat_sirasi_en_az_islenen(self):
        onceki = [{"konu_kodu": m[0]} for m in ingilizce_yaz.MUFREDAT[:3]]
        self.assertEqual(ingilizce_yaz.siradaki_konu(onceki), ingilizce_yaz.MUFREDAT[3])
        hepsi = [{"konu_kodu": m[0]} for m in ingilizce_yaz.MUFREDAT]
        self.assertEqual(ingilizce_yaz.siradaki_konu(hepsi), ingilizce_yaz.MUFREDAT[0])


class SeoBilgisi(unittest.TestCase):
    def test_tum_bolumler_seo_denetimini_gecer(self):
        for yol in sorted(SERI.glob("bolumler/[be]*.json")):
            b = json.loads(yol.read_text())
            meta, sorun = bulut3d.meta_hazirla(b, bulut3d.bolum_hatti(yol))
            self.assertEqual(sorun, [], yol.name)
            self.assertLessEqual(len(meta["baslik"] + " #shorts"), 100, yol.name)
            self.assertLessEqual(sum(len(e) + 2 for e in meta["etiketler"]), 500)
            self.assertEqual(len([w for w in meta["aciklama"].split() if w.startswith("#")]), 3)

    def test_ingilizce_baslik_anahtar_kelime_basta_ve_yerellestirme(self):
        meta, _ = bulut3d.meta_hazirla(ders(1), "ingilizce_shorts")
        self.assertTrue(meta["baslik"].startswith("İngilizce Selamlaşma: Hello"))
        self.assertIn("hello = merhaba", meta["aciklama"])
        self.assertIn("hello ne demek", meta["etiketler"])
        self.assertTrue(meta["localizations"]["en"]["title"].startswith("Learn Greetings in English"))

    def test_ayni_baslik_ikinci_kez_kullanilmaz(self):
        meta, _ = bulut3d.meta_hazirla(ders(2), "ingilizce_shorts")
        meta2, sorun = bulut3d.meta_hazirla(ders(2), "ingilizce_shorts", [meta["baslik"]])
        self.assertNotEqual(meta["baslik"], meta2["baslik"])
        self.assertEqual(sorun, [])

    def test_derleme_bilgisi(self):
        b = [{"baslik": ders(i)["baslik"], "deger": "x", "dosya": ders(i)} for i in range(1, 5)]
        meta = seo.derleme("ingilizce", "Fındık ile Pamuk", b, 3, "0:00 a\n0:40 b\n1:20 c")
        self.assertEqual(seo.denetle(meta, shorts=False), [])
        self.assertTrue(meta["baslik"].startswith("Çocuklar için İngilizce"))
        self.assertIn("apple (elma)", meta["aciklama"])
        for tur in ("haftalik", "karisik"):
            self.assertEqual(seo.denetle(seo.derleme(tur, "Fındık ile Pamuk", b, 3, "0:00 a"), shorts=False), [])


class DerlemeAyrimi(unittest.TestCase):
    def kur(self, kayit):
        yol = Path(tempfile.mkdtemp()) / "kayit.json"
        yol.write_text(json.dumps(kayit))
        return mock.patch.object(derleme, "KAYIT", yol)

    def test_masal_derlemesine_ders_ingilizceye_masal_girmez(self):
        simdi = datetime.now(timezone.utc)
        gecmis = (simdi - timedelta(days=1)).isoformat()
        kayit = [{"tarih": "2026-11-01T00:00:00+00:00", "profil": "shorts", "durum": "yuklendi", "bolum": p,
                  "yayin_zamani": gecmis} for p in [B.format(1), E.format(1), B.format(2), E.format(2),
                                                    B.format(3), E.format(3), E.format(4)]]
        with self.kur(kayit):
            haftalik = derleme.sec()
            ing = derleme.sec_karisik(tur="ingilizce")
        self.assertEqual(haftalik, [B.format(1), B.format(2), B.format(3)])
        self.assertEqual(ing, [E.format(i) for i in range(1, 5)])


if __name__ == "__main__":
    unittest.main()
