"""Derleme içeriği: mini dizi ortadan başlamaz; Uyku Öncesi derlemesine macera bölümü girmez; kapak bekleyenleri bulunur."""
import json
import unittest
from unittest import mock

import derleme
import kapak_tekrar


class Butunluk(unittest.TestCase):
    def test_mini_dizi_aralik_varsa_sonrakiler_cikar(self):
        p = [{"bolum": f"seri/findik-ile-pamuk/bolumler/{b}.json"} for b in ("b001", "b044", "b045", "b046")]  # Hazine Avı 3,4,5 (1-2 yok)
        kalan, neden = derleme.dizi_butunlugu(p)
        self.assertEqual([x["bolum"] for x in kalan], ["seri/findik-ile-pamuk/bolumler/b001.json"])
        self.assertEqual(len(neden), 3)

    def test_tam_mini_dizi_kalir(self):
        p = [{"bolum": f"seri/findik-ile-pamuk/bolumler/{b}.json"} for b in ("b042", "b043", "b044")]
        kalan, neden = derleme.dizi_butunlugu(p)
        self.assertEqual(len(kalan), 3)
        self.assertEqual(neden, [])

    def test_uyku_oncesi_macera_almaz(self):
        kayit = [{"profil": "shorts", "durum": "yuklendi", "bolum": f"seri/findik-ile-pamuk/bolumler/{b}.json"} for b in
                 ("b001", "b002", "b003", "b004", "b007", "b008", "b009", "b012", "b042", "b043", "b044")]
        with mock.patch.object(derleme, "kayitlar", return_value=kayit):
            secilen = derleme.sec_karisik()
        self.assertTrue(secilen)
        self.assertFalse(any(b.endswith(("b042.json", "b043.json", "b044.json")) for b in secilen))

    def test_kapak_bekleyenleri(self):
        # canlı yayin_kaydi.json'a bağlı değil (kapak yüklenince test kırılıyordu, 2026-11-26): geçici örnek veriyle
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "kapaklar").mkdir()
            for v in ("BEKLEYEN01", "YUKLENDI01"):
                (t / "kapaklar" / f"{v}.jpg").write_bytes(b"x")
            (t / "yayin_kaydi.json").write_text(json.dumps([
                {"profil": "derleme", "video_id": "BEKLEYEN01", "kapak": "yuklenemedi: 403"},
                {"profil": "derleme", "video_id": "YUKLENDI01", "kapak": "yuklenemedi: 403"},
                {"profil": "derleme", "video_id": "RESIMSIZ01", "kapak": "yuklenemedi: 403"},
                {"profil": "shorts", "video_id": "SHORTS01", "kapak": "yuklenemedi: 403"}]))
            (t / "durum.json").write_text(json.dumps({"YUKLENDI01": "yuklendi"}))
            with mock.patch.object(kapak_tekrar, "KOK", t), mock.patch.object(kapak_tekrar, "KAPAKLAR", t / "kapaklar"), \
                    mock.patch.object(kapak_tekrar, "DURUM", t / "durum.json"):
                vids, _ = kapak_tekrar.bekleyenler()
        self.assertEqual(vids, ["BEKLEYEN01"])


if __name__ == "__main__":
    unittest.main()
