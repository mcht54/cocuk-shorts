"""İçerik stratejisti kuralları + ölçüm bloğu (kural 8)."""
import json
import tempfile
import unittest
from pathlib import Path

from ortak import icerik_kurallari as k


def _depo(n, durum="public"):
    d = Path(tempfile.mkdtemp())
    (d / "otonom").mkdir()
    (d / "b").mkdir()
    videolar, kayit = [], []
    for i in range(n):
        yol = f"b/b{i:03d}.json"
        (d / yol).write_text(json.dumps({"baslik": f"Bölüm {i}", "ekran_basligi": f"Soru {i}?",
                                         "cekimler": [{"satirlar": [{"metin": f"ilk {i}"}]}]}))
        videolar.append({"video_id": f"v{i}", "profil": "shorts", "ad": f"Bölüm {i}", "yayin": "2026-11-01",
                         "izlenme": i * 10, "durum": durum})
        kayit.append({"video_id": f"v{i}", "bolum": yol})
    (d / "otonom" / "izlenme.json").write_text(json.dumps({"tarih": "2026-11-26T10:00:00+00:00", "videolar": videolar}))
    (d / "yayin_kaydi.json").write_text(json.dumps(kayit))
    return d


def _merak(n, profil="shorts"):
    d = Path(tempfile.mkdtemp())
    (d / "konular" / "k1").mkdir(parents=True)
    videolar = []
    for i in range(n):
        (d / "konular" / "k1" / f"kisa{i}.json").write_text(json.dumps(
            {"baslik": f"Kısa {i}", "ekran_basligi": f"Ekran {i}", "parcalar": [{"metin": f"Açılış {i}."}]}))
        videolar.append({"video_id": f"m{i}", "konu": "k1", "senaryo": f"kisa{i}", "profil": profil,
                         "yayin": "2026-11-01" if i else "2026-11-25", "izlenme": i * 100, "durum": "public"})
    (d / "izlenme.json").write_text(json.dumps({"tarih": "2026-11-26T10:00:00+00:00", "videolar": videolar}))
    return d


class Test(unittest.TestCase):
    def test_merak_olcum(self):
        o = k.merak_olcum_blogu("shorts", merak=_merak(8))
        self.assertIn("«Kısa 7» açılış: Ekran 7 | Açılış 7. — 700 izlenme", o)
        self.assertNotIn("Kısa 0»", o)  # 3 günden yeni: sayılmaz
        self.assertEqual(k.merak_olcum_blogu("shorts", merak=_merak(6)), "")  # 1 tanesi yeni -> 5 ölçüm
        self.assertEqual(k.merak_olcum_blogu("uzun", merak=_merak(8)), "")
        self.assertEqual(k.merak_olcum_blogu("shorts", merak=Path(tempfile.mkdtemp())), "")

    def test_merak_eslestir(self):
        from merak import izlenme
        kayit = [{"durum": "yuklendi", "video_id": "a", "konu": "k", "senaryo": "uzun", "profil": "uzun",
                  "yayin_zamani": "2026-11-02T10:00:00"}, {"durum": "kalite_kaldi", "konu": "x"}]
        kanal = [{"video_id": "a", "baslik": "X"}, {"video_id": "b", "baslik": "Batık Şehir! #shorts", "yayin": "2026-11-03T1"},
                 {"video_id": "c", "baslik": "Başka"}]
        e = izlenme.eslestir(kayit, kanal, {izlenme.baslik_norm("Batık şehir!"): ("pr", "kisa2", "shorts")})
        self.assertEqual([(v["video_id"], v["senaryo"]) for v in e], [("a", "uzun"), ("b", "kisa2")])
        self.assertEqual(e[1]["yayin"], "2026-11-03")

    def test_merak_toplayici_anahtarsiz_atlar(self):
        import os
        from unittest import mock
        from merak import izlenme
        with mock.patch.dict(os.environ, {"YT_REFRESH_TOKEN": ""}):
            self.assertEqual(izlenme.main(), 0)

    def test_metin_kural_ve_cocuk(self):
        m = k.metin(cocuk=True, son_acilislar=["A | b"])
        self.assertIn("EN AZ 5 KANCA", m)
        self.assertIn("Çocuk kanalı uyarlaması", m)
        self.assertIn("kanca_adaylari", m)
        self.assertIn("- A | b", m)

    def test_olcum_yeterli_veri(self):
        o = k.olcum_blogu("b", depo=_depo(8))
        self.assertIn("EN ÇOK İZLENEN", o)
        self.assertIn("«Bölüm 7» açılış: Soru 7? | ilk 7 — 70 izlenme", o)
        self.assertIn("«Bölüm 0»", o.split("EN AZ İZLENEN")[1])

    def test_olcum_az_veri_ya_da_yanlis_tur_bos(self):
        self.assertEqual(k.olcum_blogu("b", depo=_depo(5)), "")
        self.assertEqual(k.olcum_blogu("e", depo=_depo(8)), "")
        self.assertEqual(k.olcum_blogu("b", depo=_depo(8, durum="private")), "")

    def test_olcum_dosya_yok_bozuk(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(k.olcum_blogu("b", depo=d), "")
        (d / "otonom").mkdir()
        (d / "otonom" / "izlenme.json").write_text("{bozuk")
        (d / "yayin_kaydi.json").write_text("[]")
        self.assertEqual(k.olcum_blogu("b", depo=d), "")


if __name__ == "__main__":
    unittest.main()
