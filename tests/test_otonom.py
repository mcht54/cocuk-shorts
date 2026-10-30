"""Otonom döngünün ağsız parçaları: senaryo denetimleri, sıra seçimi, bölüm tamamlama, sağlık denetimi."""
import json
import os
import re
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

    def test_uzun_parca_cumlelerden_bolunur(self):
        uzun = " ".join([f"Bu {i}. cümle tam olarak sekiz kelimeden oluşuyor burada." for i in range(5)])
        p = {"metin": uzun, "gorsel": [2], "grafik": {"tur": "sayi", "deger": "85"}}
        parcalar = yaz._bol(p)
        self.assertGreater(len(parcalar), 1)
        self.assertEqual(" ".join(x["metin"] for x in parcalar), uzun)
        self.assertTrue(all(x["gorsel"] == [2] and len(x["metin"].split()) <= yaz.PARCA_KELIME for x in parcalar))
        self.assertEqual([("grafik" in x) for x in parcalar], [True] + [False] * (len(parcalar) - 1))

    def test_alinti_noktalama_farkina_dayanikli(self):
        d = yaz.dortluler(KAYNAK)
        self.assertTrue(yaz.alinti_var("could shelter 20,000 people, with their livestock", d))
        self.assertTrue(yaz.alinti_var("in 1963", d))
        self.assertFalse(yaz.alinti_var("it was built by aliens from another galaxy", d))

    def test_grafiksiz_shorts_kaynak_sayisindan_grafik_alir(self):
        s = kisa()
        s["parcalar"][-1].pop("grafik")
        yaz.otomatik_grafik(s, self.sayilar)
        self.assertEqual([p["grafik"] for p in s["parcalar"] if p.get("grafik")],
                         [{"tur": "sayi", "deger": "20.000", "birim": "kişi"}])  # 1963 yıl, 85 küçük olan

    def test_zaman_cizelgesinden_uydurma_yil_atilir(self):
        g = {"tur": "zaman", "olaylar": [{"yil": "1963", "metin": "a"}, {"yil": "1850", "metin": "b"},
                                         {"yil": "MÖ 8. yüzyıl", "metin": "c"}, {"yil": "bugün", "metin": "d"}]}
        yaz.grafik_onar(g, self.sayilar)
        self.assertEqual([o["yil"] for o in g["olaylar"]], ["1963", "MÖ 8. yüzyıl", "bugün"])
        self.assertIsNone(yaz.grafik_hatasi(g, None, self.sayilar))

    def test_ingilizce_ve_anlatilmayan_grafik_yakalanir(self):
        self.assertEqual(yaz.ingilizce_var("As of 2021, alanın yüzde 10'u kazıldı."), ["as", "of"])
        self.assertEqual(yaz.ingilizce_var("Bu iş İstanbul'da başladı; değirmen taşını andıran kapılar."), [])
        self.assertFalse(yaz.grafik_anlatimda_mi({"tur": "sayi", "deger": "17"}, "En çok hayvan figürü var."))
        self.assertTrue(yaz.grafik_anlatimda_mi({"tur": "sayi", "deger": "20.000"}, "20.000 kişi saklanırdı."))
        self.assertIn("çarpıcı değil", yaz.grafik_hatasi({"tur": "sayi", "deger": "2"}))

    def test_yaziyla_sayi_yakalanir(self):
        h = yaz.yapi_denetimi(kisa("Bin dokuz yüz bir yılında bulundu."), 5, False, KAYNAK, self.sayilar)
        self.assertTrue(any("RAKAMLA" in x for x in h))
        self.assertIsNone(yaz.SAYI_KELIME.search("Bir yüzü taştan, iki kapısı vardı."))

    def test_anlatilmayan_grafik_metindeki_sayiyla_degisir(self):
        b = {"parcalar": [{"metin": "Burada 20.000 kişi saklanabiliyordu.", "gorsel": [0],
                           "grafik": {"tur": "sayi", "deger": "82", "birim": "parça"}}]}
        yaz._anlatilmayan_grafik(b, self.sayilar)
        self.assertEqual(b["parcalar"][0]["grafik"]["deger"], "20.000")

    def test_hatali_parca_ve_isaretli_cumle_kodla_atilir(self):
        b = {"parcalar": [{"metin": "Burada 20.000 kişi saklanabiliyordu.", "gorsel": [0]},
                          {"metin": "Tam 4321 yıl önce yapıldı.", "gorsel": [0]},
                          {"metin": "This city was very deep.", "gorsel": [0]},
                          {"metin": "Uzaylılar şehri bir gecede kazdı.", "gorsel": [0]}], "iddialar": []}
        self.assertEqual(len(yaz.ayikla(b, self.sayilar)), 2)
        self.assertTrue(yaz.cumleleri_at(b, ["Uzaylılar şehri bir gecede kazdı"], self.sayilar))
        self.assertEqual([p["metin"] for p in b["parcalar"]], ["Burada 20.000 kişi saklanabiliyordu."])
        self.assertFalse(yaz.cumleleri_at(b, ["Tamamen başka bir cümle"], self.sayilar))

    def test_uydurma_alinti_reddedilir(self):
        s = kisa()
        for i in s["iddialar"]:
            i["kaynak_alinti"] = "built by aliens in 1963"
        self.assertTrue(any("alıntı" in x for x in yaz.yapi_denetimi(s, 5, False, KAYNAK, self.sayilar)))


class MerakBolumBolumTesti(unittest.TestCase):
    """Gemini taklidiyle: plan + 8 bölüm -> tam senaryo kelime/grafik/iddia denetiminden geçer."""

    def sahte_gemini(self, istem, **_):
        if "PLANINI" in istem:
            grafikler = [{"tur": "sayi", "deger": "85", "birim": "m"}, {"tur": "sayi", "deger": "20.000", "birim": "kişi"},
                         {"tur": "zaman", "olaylar": [{"yil": "1963", "metin": "keşif"}, {"yil": "MÖ 8. yüzyıl", "metin": "yapım"},
                                                      {"yil": "bugün", "metin": "müze"}]},
                         {"tur": "karsilastirma", "deger": 85, "birim": "m", "referans": "galata"},
                         {"tur": "sayi", "deger": "1963", "birim": ""}, {"tur": "sayi", "deger": "4321", "birim": "x"},
                         {"tur": "sayi", "deger": "85", "birim": "m"}, None]
            return {"baslik": "Yeraltı şehri", "kapak_yazisi": "YERİN ALTINDA", "kapak_gorsel": 99, "aciklama": "a",
                    "etiketler": ["x"], "bolumler": [{"ad": f"Bölüm {i}", "anlatilacak": ["x"], "grafik": g}
                                                     for i, g in enumerate(grafikler)]}
        if "kelime kısa" in istem:
            self.ek_istendi += 1
            eksik = int(re.search(r"(\d+) kelime kısa", istem).group(1))
            cumle = "Araştırmacılar yıllarca bu tünellerin gizemini çözmeye çalıştı."
            return {"parcalar": [{"metin": cumle, "gorsel": [3]}] * (eksik // 8 + 1),
                    "iddialar": [{"iddia": "y", "kaynak_alinti": "It extends to a depth of approximately 85 m"}]}
        if "bölümünü yaz" in istem:
            hedef = int(re.search(r"yaklaşık (\d+) kelime hedefle", istem).group(1))
            no = int(re.search(r"\) (\d+)\. bölümünü", istem).group(1))
            # 2. bölüm çok kısa (ek parça istenir), 3. uzun (kodla kırpılır), 4-8 toleransın içinde ama kısa
            # (toplam 800'ün altına düşer, sonda en kısa bölüme ek parça)
            hedef = {2: hedef // 2, 3: int(hedef * 1.6)}.get(no, int(hedef * 0.85) if no >= 4 else hedef)
            cumle = "Karanlık koridorlar yerin altında sessizce uzanıyordu ve kimse sonunu bilmiyordu."
            n = hedef // len(cumle.split())
            uzun = " ".join(["Derinlik 85 metre, nüfus 20.000 kişi, keşif 1963 yılındaydı."] + [cumle] * 2)  # bölünmeli
            parcalar = [{"metin": uzun, "gorsel": None, "grafik": True}] + [{"metin": cumle, "gorsel": [1]}] * (n - 3)
            return {"parcalar": parcalar, "iddialar": [{"iddia": "x", "kaynak_alinti": "discovered in 1963"}]}
        if "titizlikle denetle" in istem:
            return {"sorunlar": []}
        raise AssertionError(istem[:80])

    def test_plan_ve_bolumler_birlesince_denetimden_gecer(self):
        sayilar = yaz.sayilar(KAYNAK)
        ortak = dict(konu="Derinkuyu", calisma="", kurallar="", gorseller="", kaynak=KAYNAK)
        self.ek_istendi = 0
        with mock.patch.object(yaz.gemini, "sor", side_effect=self.sahte_gemini):
            s = yaz.uzun_yaz(ortak, [{}] * 5, KAYNAK, sayilar, None)
        self.assertIsNotNone(s)
        self.assertGreaterEqual(self.ek_istendi, 1)  # kısa bölüm ek parçayla tamamlandı; uzun bölüm kodla kırpıldı
        self.assertGreaterEqual(sum(len(p["metin"].split()) for b in s["bolumler"] for p in b["parcalar"]),
                                yaz.UZUN_KELIME[0])
        self.assertEqual(len(s["bolumler"]), 8)
        grafikler = [p["grafik"] for b in s["bolumler"] for p in b["parcalar"] if p.get("grafik")]
        self.assertEqual(len(grafikler), 6)  # kaynakta olmayan 4321 kodla atıldı
        self.assertEqual(s["kapak_gorsel"], 0)
        self.assertTrue(all(p["gorsel"] for b in s["bolumler"] for p in b["parcalar"]))
        self.assertEqual(yaz.yapi_denetimi(s, 5, True, KAYNAK, sayilar), [])


class MerakEkranYazisiTesti(unittest.TestCase):
    def test_gorsel_tekrari_sinirlanir(self):
        s = {"parcalar": [{"metin": "x", "gorsel": [7]} for _ in range(20)]}
        yaz.gorsel_dengele(s, 30)
        g = [p["gorsel"][0] for p in s["parcalar"]]
        self.assertLessEqual(max(g.count(x) for x in g), 1)
        self.assertTrue(all(a != b for a, b in zip(g, g[1:])))

    def test_harfsiz_turkce_metinden_duzelir(self):
        s = {"ekran_basligi": "Gizemli Dikilitaslar", "baslik": "Ilk Tapinak",
             "parcalar": [{"metin": "Bu dikilitaşlar ilk tapınak sayılır.", "yazi": "DIKILITASLAR",
                           "grafik": {"tur": "harita", "etiket": "Sanliurfa"}}]}
        yaz.turkce_onar(s, "Şanlıurfa ilinde.")
        self.assertEqual(s["ekran_basligi"], "Gizemli Dikilitaşlar")
        self.assertEqual(s["baslik"], "İlk Tapınak")
        self.assertEqual(s["parcalar"][0]["yazi"], "DİKİLİTAŞLAR")
        self.assertEqual(s["parcalar"][0]["grafik"]["etiket"], "Şanlıurfa")

    def test_imla_yalniz_harf_duzeltmesini_kabul_eder(self):
        s = {"baslik": "Gobekli Tepe", "ekran_basligi": "Sifir Noktasi", "parcalar": []}
        cevap = {"baslik": "Göbekli Tepe", "ekran_basligi": "Tamamen Başka Başlık"}
        with mock.patch.object(yaz.gemini, "sor", return_value=cevap):
            yaz.imla_duzelt(s)
        self.assertEqual(s["baslik"], "Göbekli Tepe")
        self.assertEqual(s["ekran_basligi"], "Sifir Noktasi")
        self.assertTrue(s["imla"])


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
