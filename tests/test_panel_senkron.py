"""Panel İçerik takvimi senkronu: yüklenen bölüm kilitli, sıradaki bölüm düzenlenir; uzun/bozuk düzenleme reddedilir; panel düşse de hat durmaz."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from otonom import panel_senkron as P


class PanelSenkron(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        seri = self.tmp / "seri"
        (seri / "bolumler").mkdir(parents=True)
        (seri / "seri.json").write_text((P.SERI / "seri.json").read_text())
        ornek = sorted(P.SERI.glob("bolumler/b*.json"))[-1]
        for ad in ("b900.json", "b901.json"):
            (seri / "bolumler" / ad).write_text(ornek.read_text())
        kayit = self.tmp / "yayin_kaydi.json"
        kayit.write_text(json.dumps([{"bolum": "seri/findik-ile-pamuk/bolumler/b900.json", "profil": "shorts", "durum": "yuklendi",
                                      "video_id": "v1", "tarih": "2099-01-01T10:00:00+00:00", "youtube": {"publishAt": "2099-01-02T14:00:00Z"}}]))
        self.seri = seri
        self.yamalar = [mock.patch.object(P, "SERI", seri), mock.patch.object(P, "KAYIT", kayit)]
        for y in self.yamalar:
            y.start()

    def tearDown(self):
        for y in self.yamalar:
            y.stop()

    def test_ozet_ve_uygula(self):
        o = {b["id"]: b for b in P.takvim_ozeti()}
        self.assertEqual(o["b900"]["durum"], "zamanlandi")
        self.assertFalse(o["b900"]["duzenlenebilir"])
        self.assertTrue(o["b901"]["duzenlenebilir"])
        sid, eski = o["b901"]["satirlar"][0]["id"], o["b901"]["satirlar"][0]["metin"]
        uyg, ret = P.uygula([{"id": "a", "bolum_id": "b901", "satirlar": {sid: eski + " Haydi!"}},
                             {"id": "b", "bolum_id": "b900", "satirlar": {sid: "x"}},
                             {"id": "c", "bolum_id": "b901", "satirlar": {sid: eski + " bir iki üç dört beş"}},
                             {"id": "d", "bolum_id": "../x", "satirlar": {}}])
        self.assertEqual(uyg, ["a"])
        self.assertEqual({r["id"] for r in ret}, {"b", "c", "d"})
        self.assertTrue(json.loads((self.seri / "bolumler" / "b901.json").read_text())["cekimler"][0]["satirlar"][0]["metin"].endswith("Haydi!"))

    def test_panel_dusse_de_hat_durmaz(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACTIONS_ID_TOKEN_REQUEST_URL", None)
            self.assertEqual(P.main("al"), 0)


if __name__ == "__main__":
    unittest.main()
