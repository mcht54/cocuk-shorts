"""Merak Arşivi konu bulucu: Gemini aday önerir, Wikipedia/Commons/okunma verisi doğrular, en ilgi çekeni seçer.

Bir konu ancak şunları sağlarsa kabul edilir: İngilizce Wikipedia makalesi var (anlam ayrımı değil),
EN+TR kaynak metni yeterince uzun, en az GORSEL_EN_AZ serbest lisanslı fotoğraf var, daha önce işlenmemiş.
Seçilen konunun kaynak paketi merak/konular/<kimlik>/kaynak.json + gorseller.json olarak yazılır.
"""
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from ortak import gemini
from merak import kaynak

KOK = Path(__file__).resolve().parent
KONULAR = KOK / "konular"
KAYNAK_EN_AZ = 9000       # EN + TR düz metin karakteri
GORSEL_EN_AZ = 18
KATEGORILER = [
    "gizemli antik yapılar ve kayıp şehirler", "tarihin çözülememiş gizemleri", "olağanüstü doğa olayları",
    "uzay ve gökbilim", "dünyanın en tuhaf yerleri", "antik uygarlıklar ve icatları",
    "derin okyanus ve keşifler", "şaşırtıcı hayvanlar ve evrim", "efsanevi kayıp hazineler ve batıklar",
    "Türkiye ve Anadolu'nun gizemli tarihi", "büyük mühendislik harikaları", "jeoloji ve volkanlar",
    "tarihî keşif yolculukları", "bilim tarihinin dönüm noktaları", "terk edilmiş yerler",
]

ONERI_ISTEMI = """Türkçe bir YouTube belgesel kanalı ("Merak Arşivi": gizem, tarih, bilim, doğa) için konu öner.
Bu turun ağırlıklı alanı: {kategori}

Kurallar:
- {adet} aday. Her biri GERÇEK, belgelenmiş bir konu; İngilizce Wikipedia'da kendi makalesi olan (tam makale başlığını ver).
- Geniş kitleyi meraklandıracak, görsel olarak zengin (fotoğrafı bol) konular. Türkiye/Anadolu konuları artı puan.
- YASAK: yaşayan kişiler, son 20 yılın felaket/terör/savaş olayları, siyaset, din tartışması, sağlık tavsiyesi,
  komplo teorisi propagandası, şiddet/vahşet ağırlıklı konular, intihar, cinsellik.
- Şu konular daha önce işlendi, benzerlerini önerme: {gecmis}

Yalnızca JSON dizi döndür:
[{{"wiki": "İngilizce Wikipedia başlığı", "calisma_basligi": "Türkçe merak uyandıran başlık", "arama": ["Commons görsel araması için 1-2 İngilizce terim"]}}]"""


def kimlik(metin):
    m = unicodedata.normalize("NFKD", metin.lower().replace("ı", "i"))
    m = "".join(c for c in m if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", m).strip("-")[:50]


def islenenler():
    return sorted(p.name for p in KONULAR.glob("*") if (p / "kaynak.json").exists())


def _paket(aday):
    """Adayı doğrula; uygunsa (puan, paket, görseller), değilse (None, neden)."""
    en = kaynak.makale(aday["wiki"], "en")
    if not en:
        return None, "Wikipedia makalesi yok / anlam ayrımı"
    kid = kimlik(en["baslik"])
    if (KONULAR / kid / "kaynak.json").exists():
        return None, "zaten işlendi"
    tr_baslik = en["diller"].get("tr")
    tr = kaynak.makale(tr_baslik, "tr") if tr_baslik else None
    uzunluk = en["uzunluk"] + (tr["uzunluk"] if tr else 0)
    if uzunluk < KAYNAK_EN_AZ:
        return None, f"kaynak metin kısa ({uzunluk})"
    gorseller = kaynak.gorseller(en["baslik"], aday.get("arama", [])[:2])
    if len(gorseller) < GORSEL_EN_AZ:
        return None, f"görsel az ({len(gorseller)})"
    okunma = kaynak.goruntulenme(en["baslik"])
    paket = {"kimlik": kid, "wiki": en["baslik"], "calisma_basligi": aday.get("calisma_basligi", ""),
             "okunma_60g": okunma, "koordinat": kaynak.koordinat(en["baslik"]), "kaynaklar": [en["url"]] + ([tr["url"]] if tr else []),
             "metin_en": en["metin"][:40000], "metin_tr": (tr["metin"][:20000] if tr else ""),
             "tarih": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    # ilgi (okunma) + görsel zenginliği; Türkçe makalesi olan konulara küçük öncelik
    puan = okunma * (1.3 if tr else 1.0) * min(1.0, len(gorseller) / 40)
    return (puan, paket, gorseller), None


def yeni_konu(tur=0):
    """Bir konu seçip paketini yazar; konu kimliğini döner (bulunamazsa None)."""
    gecmis = islenenler()
    kategori = KATEGORILER[(len(gecmis) + tur) % len(KATEGORILER)]
    adaylar = gemini.sor(ONERI_ISTEMI.format(kategori=kategori, adet=10,
                                              gecmis=", ".join(gecmis[-150:]) or "yok"), sicaklik=1.0)
    if isinstance(adaylar, dict):
        adaylar = next((v for v in adaylar.values() if isinstance(v, list)), [])
    uygun = []
    for a in adaylar[:10]:
        if not isinstance(a, dict) or not a.get("wiki"):
            continue
        try:
            sonuc, neden = _paket(a)
        except Exception as e:  # tek adayın ağ hatası turu bozmasın
            sonuc, neden = None, f"hata: {e}"
        print(f"  aday {a['wiki']!r}: {'uygun' if sonuc else neden}", flush=True)
        if sonuc:
            uygun.append(sonuc)
    if not uygun:
        return None
    _, paket, gorseller = max(uygun, key=lambda x: x[0])
    d = KONULAR / paket["kimlik"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "kaynak.json").write_text(json.dumps(paket, ensure_ascii=False, indent=1))
    (d / "gorseller.json").write_text(json.dumps(gorseller, ensure_ascii=False, indent=1))
    print(f"konu seçildi: {paket['kimlik']} (okunma {paket['okunma_60g']}, {len(gorseller)} görsel)")
    return paket["kimlik"]
