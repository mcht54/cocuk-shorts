"""Otonom döngünün ağsız parçaları: senaryo denetimleri, sıra seçimi, bölüm tamamlama, sağlık denetimi."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from merak import yaz, yayinla
from otonom import masal_yaz, saglik, takvim

DEPO = Path(__file__).resolve().parent.parent
SERI = DEPO / "seri" / "findik-ile-pamuk"
KAYNAK = ("The city was discovered in 1963. It extends to a depth of approximately 85 m and could shelter "
          "20,000 people with their livestock. Construction began in the 8th century BC.")


def kisa(metin_ek="", gorsel=0):
    parca = ["Yerin altında bir şehir düşünün.", "1963 yılında bir duvar yıkıldı.",
             "Arkasından 85 metre derine inen tüneller çıktı.", f"Burada 20.000 kişi saklanabiliyordu. {metin_ek}",
             "Peki bunu kim kazdı?", "Tüm hikâye kanalda."]
    dolgu = " ".join(["Karanlık koridorlar sessizce uzanıyordu."] * 14)
    return {"baslik": "Yeraltı şehri", "ekran_basligi": "85 metre derinde",
            "parcalar": [{"metin": m, "gorsel": [gorsel]} for m in parca] + [{"metin": dolgu[:150], "gorsel": [1],
                                                                      "grafik": {"tur": "sayi", "deger": "85", "birim": "m"}}],
            "iddialar": [{"iddia": "x", "kaynak_alinti": "discovered in 1963"},
                         {"iddia": "y", "kaynak_alinti": "approximately 85 m"},
                         {"iddia": "z", "kaynak_alinti": "20,000 people"}]}


class MerakDenetimTesti(unittest.TestCase):
    def setUp(self):
        self.sayilar = yaz.sayilar(KAYNAK)

    def test_binlik_ayiraclar_esitlenir(self):
        self.assertIn("20000", self.sayilar)
        self.assertEqual(yaz.sayilar("20.000 kişi, 1,5 km"), {"20000", "1.5"})

    def test_kaynakta_olmayan_sayi_yakalanir(self):
        self.assertEqual(yaz.sayi_denetimi("1963 yılında 40.000 kişi", self.sayilar), ["40000"])
        self.assertEqual(yaz.sayi_denetimi("8 kat ve 3 kapı", self.sayilar), [])  # küçük sayımlar serbest

    def test_dogru_kisa_senaryo_gecer(self):
        h = yaz.yapi_denetimi(kisa(), 5, False, KAYNAK, self.sayilar)
        self.assertEqual([x for x in h if "kelime" not in x], [])

    def test_uydurma_sayi_ve_gecersiz_gorsel_reddedilir(self):
        h = yaz.yapi_denetimi(kisa("Tam 3000 yıl önce.", gorsel=9), 5, False, KAYNAK, self.sayilar)
        self.assertTrue(any("3000" in x for x in h))
        self.assertTrue(any("gorsel" in x for x in h))

    def test_grafiksiz_ya_da_uydurma_grafik_reddedilir(self):
        s = kisa()
        s["parcalar"][-1].pop("grafik")
        self.assertTrue(any("grafik" in x for x in yaz.yapi_denetimi(s, 5, False, KAYNAK, self.sayilar)))
        s["parcalar"][-1]["grafik"] = {"tur": "karsilastirma", "deger": 85, "birim": "m", "referans": "ay"}
        self.assertTrue(any("referans" in x for x in yaz.yapi_denetimi(s, 5, False, KAYNAK, self.sayilar)))

    def test_bos_alanli_yanit_cokmez_hataya_doner(self):
        s = kisa()
        s["parcalar"][0]["yazi"] = None
        s["parcalar"][1]["metin"] = None
        s["parcalar"][2]["grafik"] = None
        s["baslik"] = None
        s["iddialar"] = None
        h = yaz.yapi_denetimi(yaz._duzenle(s), 5, False, KAYNAK, self.sayilar)
        self.assertTrue(any("başlık" in x for x in h))
        self.assertIsNone(yaz._duzenle(["liste"]))
        u = {"baslik": "x", "bolumler": [None, {"ad": None, "parcalar": [None, {"metin": None, "gorsel": [0]}]}]}
        self.assertTrue(yaz.yapi_denetimi(yaz._duzenle(u), 5, True, KAYNAK, self.sayilar))

    def test_uydurma_alinti_reddedilir(self):
        s = kisa()
        for i in s["iddialar"]:
            i["kaynak_alinti"] = "built by aliens in 1963"
        self.assertTrue(any("alıntı" in x for x in yaz.yapi_denetimi(s, 5, False, KAYNAK, self.sayilar)))


class MerakSiraTesti(unittest.TestCase):
    def test_shorts_konular_arasinda_doner_ve_yuklenen_tekrarlanmaz(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for i, kid in enumerate(["a", "b"]):
                (d / kid).mkdir()
                (d / kid / "kaynak.json").write_text(json.dumps({"tarih": f"2026-10-0{i + 1}"}))
                for ad in ("uzun", "kisa1", "kisa2"):
                    (d / kid / f"{ad}.json").write_text("{}")
            kayit = d / "kayit.json"
            kayit.write_text(json.dumps([
                {"konu": "a", "senaryo": "uzun", "profil": "uzun", "durum": "yuklendi"},
                {"konu": "a", "senaryo": "kisa1", "profil": "shorts", "durum": "yuklendi"},
                {"konu": "b", "senaryo": "kisa1", "profil": "shorts", "durum": "kalite_kaldi"},
                {"konu": "b", "senaryo": "kisa1", "profil": "shorts", "durum": "kalite_kaldi"}]))
            with mock.patch.object(yayinla, "KONULAR", d), mock.patch.object(yayinla, "KAYIT", kayit):
                self.assertEqual(yayinla.sira("uzun"), [("b", "uzun")])
                # a'nın uzunu yayında -> önce a; son Shorts a olduğu için sırada b önde; iki kez kalan atlanır
                self.assertEqual(yayinla.sira("shorts"), [("b", "kisa2"), ("a", "kisa2")])


class MasalYazTesti(unittest.TestCase):
    def test_mevcut_bolum_tamamlanip_denetimden_gecer(self):
        seri = json.loads((SERI / "seri.json").read_text())
        b = json.loads((SERI / "bolumler" / "b047.json").read_text())
        ham = {k: b[k] for k in ("baslik", "deger", "mekan", "muzik", "baslangic", "nesne_yerlesim",
                                 "ekran_basligi", "cekimler")}
        ham["aciklama"] = "Yarış günü!"
        t = masal_yaz._tamamla(ham, 999, seri)
        self.assertEqual(t["youtube"]["baslik"], "Fındık ile Pamuk | Büyük Yarış | 3D Çocuk Çizgi Filmi")
        self.assertEqual(masal_yaz._denetle(t, seri, set()), [])
        self.assertTrue(any("başlık" in h for h in masal_yaz._denetle(t, seri, {"büyük yarış"})))

    def test_bozuk_yanit_cokmez_hata_doner(self):
        seri = json.loads((SERI / "seri.json").read_text())
        t = masal_yaz._tamamla({"cekimler": [{"tip": "orta"}]}, 999, seri)
        self.assertTrue(masal_yaz._denetle(t, seri, set()))


class SaglikTesti(unittest.TestCase):
    def test_son_yukleme_ve_sessizlik(self):
        simdi = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "k.json").write_text(json.dumps([
                {"profil": "shorts", "durum": "yuklendi", "tarih": (simdi - timedelta(hours=60)).isoformat()},
                {"profil": "shorts", "durum": "kalite_kaldi", "tarih": simdi.isoformat()}]))
            with mock.patch.object(saglik, "DEPO", Path(d)):
                son = saglik.son_yukleme("k.json", lambda k: k["profil"] == "shorts")
        self.assertLess(son, simdi - timedelta(hours=50))

    def test_baslamamis_merak_hatti_uyari_vermez(self):
        with mock.patch.dict(os.environ, {"YAYIN": "acik", "MERAK_BASLANGIC": "", "DERLEME_BASLANGIC": "",
                                          "GEMINI_API_KEY": "x", "RUNNER_TEMP": tempfile.gettempdir()}), \
                mock.patch.object(saglik, "token_dene", return_value=None), \
                mock.patch.object(saglik, "DEPO", Path(tempfile.mkdtemp())):
            (saglik.DEPO / "otonom").mkdir()
            saglik.main()
            metin = (Path(tempfile.gettempdir()) / "saglik.md").read_text()
        self.assertNotIn("Merak Arşivi Shorts:", metin.split("Sorunlar")[-1] if "Sorunlar" in metin else "")


class TakvimTesti(unittest.TestCase):
    def test_bos_slotlar_dolu_olanlari_atlar(self):
        simdi = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)  # pazartesi
        bos = takvim.bos_slotlar("merak_uzun", [], simdi)
        self.assertEqual([s.weekday() for s in bos], [1, 4])  # salı, cuma
        kayit = [{"durum": "yuklendi", "yayin_zamani": bos[0].isoformat()}]
        self.assertEqual(takvim.bos_slotlar("merak_uzun", kayit, simdi), bos[1:])
        self.assertEqual(len(takvim.bos_slotlar("masal_shorts", [], simdi)), 7)

    def test_gecmek_uzere_olan_slot_hemen_yayinlanir(self):
        simdi = datetime(2026, 11, 2, 13, 50, tzinfo=timezone.utc)
        slot = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
        self.assertEqual(takvim.yukleme_zamani(slot, simdi), (None, simdi))
        sonra = slot + timedelta(days=3)
        self.assertEqual(takvim.yukleme_zamani(sonra, simdi), (sonra, sonra))


if __name__ == "__main__":
    unittest.main()
