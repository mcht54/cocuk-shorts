import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import derleme


class SecimTesti(unittest.TestCase):
    def _kayit(self, kayitlar):
        d = tempfile.mkdtemp()
        yol = Path(d) / "yayin_kaydi.json"
        yol.write_text(json.dumps(kayitlar))
        return mock.patch.object(derleme, "KAYIT", yol)

    def test_yalniz_yuklenmis_ve_derlenmemis_shortslar(self):
        b = [f"seri/findik-ile-pamuk/bolumler/b{n:03d}.json" for n in range(1, 6)]
        kayitlar = [{"bolum": b[0], "profil": "shorts", "durum": "uretildi"}]
        kayitlar += [{"bolum": x, "profil": "shorts", "durum": "yuklendi"} for x in b]
        kayitlar.append({"bolum": "derleme", "profil": "derleme", "durum": "yuklendi", "parcalar": [b[0]],
                         "youtube": {"privacyStatus": "public"}})
        with self._kayit(kayitlar):
            self.assertEqual(derleme.sec(), b[1:])

    def test_gizli_deneme_derlemesi_bolum_tuketmez(self):
        b = [f"seri/findik-ile-pamuk/bolumler/b{n:03d}.json" for n in range(1, 4)]
        kayitlar = [{"bolum": x, "profil": "shorts", "durum": "yuklendi"} for x in b]
        kayitlar.append({"bolum": "derleme", "profil": "derleme", "durum": "yuklendi", "parcalar": b,
                         "youtube": {"privacyStatus": "private"}})
        with self._kayit(kayitlar):
            self.assertEqual(derleme.sec(), b)

    def test_yetersiz_bolumde_derleme_yok(self):
        with self._kayit([{"bolum": "seri/findik-ile-pamuk/bolumler/b001.json", "profil": "shorts",
                           "durum": "yuklendi"}]):
            self.assertEqual(derleme.sec(), [])

    def test_elle_secim(self):
        self.assertEqual(derleme.sec(["2", "3", "4"])[0], "seri/findik-ile-pamuk/bolumler/b002.json")


if __name__ == "__main__":
    unittest.main()
