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


class Test(unittest.TestCase):
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
