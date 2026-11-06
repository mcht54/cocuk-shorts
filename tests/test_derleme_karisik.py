import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import derleme


class KarisikDerlemeTesti(unittest.TestCase):
    def kur(self, kayit):
        d = Path(tempfile.mkdtemp())
        yol = d / "kayit.json"
        yol.write_text(json.dumps(kayit))
        return mock.patch.object(derleme, "KAYIT", yol)

    def test_az_kullanilan_once_ve_yayinlanmamis_yok(self):
        simdi = datetime(2026, 11, 11, 8, tzinfo=timezone.utc)
        bolumler = [f"seri/findik-ile-pamuk/bolumler/b{i:03d}.json" for i in range(1, 13)]
        kayit = [{"tarih": "2026-10-30T00:00:00+00:00", "profil": "shorts", "durum": "yuklendi", "bolum": b,
                  "yayin_zamani": (simdi - timedelta(days=1)).isoformat()} for b in bolumler[:11]]
        kayit.append({"tarih": "2026-10-30T00:00:00+00:00", "profil": "shorts", "durum": "yuklendi",
                      "bolum": bolumler[11], "yayin_zamani": (simdi + timedelta(days=1)).isoformat()})
        kayit.append({"tarih": "2026-11-04T08:00:00+00:00", "profil": "derleme", "tur": "karisik",
                      "durum": "yuklendi", "parcalar": bolumler[:3]})
        with self.kur(kayit), mock.patch.object(derleme, "KARISIK_EN_COK", 8):
            s = derleme.sec_karisik(simdi)
        self.assertEqual(len(s), 8)
        self.assertNotIn(bolumler[11], s)           # henüz yayınlanmamış
        self.assertTrue(set(bolumler[3:11]) == set(s))  # önce hiç kullanılmamışlar

    def test_ayni_hafta_ikinci_kez_yapilmaz(self):
        simdi = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)
        kayit = [{"tarih": "2026-11-11T09:00:00+00:00", "profil": "derleme", "tur": "karisik",
                  "durum": "yuklendi", "parcalar": []}]
        with self.kur(kayit):
            self.assertEqual(derleme.sec_karisik(simdi), [])


if __name__ == "__main__":
    unittest.main()
