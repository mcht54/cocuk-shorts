"""Fındık ile Pamuk için yeni bölüm yazarı (Gemini): seri sözlüğüyle sınırlı bölüm JSON'u yazar,
render öncesi denetimden (cocuk3d.bolum_denetle) ve çocuk güvenliği denetiminden geçirir.

Denetimi geçemeyen bölüm hatalarıyla birlikte Gemini'ye düzelttirilir; DENEME turda geçemezse yazılmaz.
Çocuklar sakin bölümleri erken terk ettiği için (2026-10 gözlem) bölümlerin çoğu macera/aksiyon ağırlıklıdır.
"""
import json
import random
import re
from pathlib import Path

from cocuk.senaryo import DENETIM_ISTEMI
from cocuk3d import bolum_denetle
from ortak import gemini

DEPO = Path(__file__).resolve().parent.parent
SERI = DEPO / "seri" / "findik-ile-pamuk"
DENEME = 4
ORNEKLER = ["b047", "b045", "b043", "b001"]
DEGERLER = [
    "paylaşmak", "dürüstlük", "cesaret", "yardımlaşma", "sabır", "özür dilemek", "takım çalışması", "azim",
    "empati", "sorumluluk", "doğayı korumak", "merak etmek", "kendine güvenmek", "sıra beklemek", "teşekkür etmek",
    "kurallara uymak", "farklılıklara saygı", "planlı olmak", "dikkatli olmak", "arkadaşını dinlemek",
    "yeni şeyler denemek", "hatadan ders çıkarmak", "cömertlik", "söz tutmak", "problem çözmek",
    "sayıları öğrenmek", "renkleri tanımak", "şekilleri tanımak", "yön bulmak", "sakin kalmak",
]

ISTEM = """Sen 3-7 yaş için 3D çizgi film dizisi "Fındık ile Pamuk"un senaristisin. YENİ bir Shorts bölümü yaz.

SERİ: {seri_aciklama}
Karakterler: findik (Fındık: meraklı, enerjik, cömert sincap), pamuk (Pamuk: yumuşak kalpli, düşünceli tavşan),
anlatici (yalnız ses; görünmez).

Bu bölüm: {tur}. İşlenecek değer: "{deger}".
Daha önce yazılmış bölümler (başlık | değer) — aynı hikâyeyi TEKRARLAMA, yeni bir olay kur:
{gecmis}

SÖZLÜK (yalnız bunlar; başka değer YAZMA):
- mekan: {mekanlar}
- nesne: {nesneler}  (sandik taşınamaz, yalnız "ac" ile açılır; nesne_yerlesim: {{"nesne": [x, y, 0.0]}})
- çekim tip: {tipler}; hareket: {hareketler}; isik: {isiklar}
- eylemler: yuru/kos/atla {{"nereye": [x, y], "son": 0-1}}, zipla {{"kez": 1-3, "son"}}, el_salla {{"son"}},
  tut {{"nesne"}}, ver {{"nesne", "kime"}}, ac {{"nesne": "sandik"}}, ifade {{"tur": {ifadeler}}},
  bak {{"kime": karakter}} ya da {{"yon": -1..1}}, otur, kalk. Her eylemde "kim" ve "bas" (0-1, çekim içi zaman).

KURALLAR (otomatik denetlenir):
- Sahne: x {sx}, y {sy}. Karakterler bölüm boyunca konumlarını korur (bir çekimde yürüyen sonraki çekimde oradadır).
- atla: tek sıçrayış en çok {atlayis} m. tut: karakter nesneye en çok {uzanma} m yakın olmalı (önce yürüsün).
  ver: iki karakter arası en çok {verme} m. ac: sandığa en çok 0.6 m. Otururken yürüme/zıplama yok (önce kalk).
- 5-6 çekim; her çekimde 1-3 satır; her satır EN ÇOK 12 kelime. Toplam 45-70 kelime (bölüm 25-50 sn).
- İlk çekim ilk saniyede merak/heyecan uyandırsın. Son çekimde anlatıcı değeri tek sıcak cümleyle söylesin.
- Korku, tehlike, yaralanma, kötü karakter, ceza, kayboluş YOK. Macera = keşif, yarış, bulmaca, engel aşma.
- Dil: doğru, sade, sevimli Türkçe; karakterler kısa ve canlı konuşsun.
- "ekran_basligi": ilk saniyelerde ekranda yazacak en çok 4 kelimelik merak uyandıran soru/başlık.
- "baslik": 2-4 kelimelik bölüm adı (öncekilerden farklı). "aciklama": ebeveynlere 1-2 cümle.

ÖRNEK BÖLÜMLER (biçim için; içerik kopyalama):
{ornekler}

Yalnızca şu JSON'u döndür:
{{"baslik": "", "deger": "", "mekan": "", "muzik": "macera|normal", "baslangic": {{"findik": [x, y], "pamuk": [x, y]}},
 "nesne_yerlesim": {{}}, "ekran_basligi": "", "aciklama": "", "cekimler": [ ... ]}}"""

DUZELT = """Bu çizgi film bölüm JSON'u otomatik denetimden geçemedi. Sorunlar:
{hatalar}

Sözlük ve kurallar aynı. Yalnız sorunları düzelt (hikâyeyi koru), aynı yapıda TAM JSON döndür.

{bolum}"""


def _ornek(ad):
    b = json.loads((SERI / "bolumler" / f"{ad}.json").read_text())
    return json.dumps({k: b[k] for k in ("baslik", "deger", "mekan", "muzik", "baslangic", "nesne_yerlesim",
                                         "ekran_basligi", "cekimler") if k in b}, ensure_ascii=False)


def _tamamla(b, no, seri):
    """Gemini'nin yazmadığı sabit alanlar + YouTube meta."""
    b = {k: v for k, v in b.items() if k in ("baslik", "deger", "mekan", "muzik", "baslangic", "nesne_yerlesim",
                                             "ekran_basligi", "aciklama", "cekimler")}
    baslik = re.sub(r"\s+", " ", str(b.get("baslik", ""))).strip()[:40]
    deger = str(b.get("deger", "")).strip()[:40]
    out = {"seri_id": seri["seri_id"], "bolum_no": no, "baslik": baslik, "deger": deger,
           "onceki_olaylar": [], "bu_bolumde_degisen": [], "mekan": b.get("mekan"),
           "baslangic": b.get("baslangic", {}), "nesne_yerlesim": b.get("nesne_yerlesim") or {},
           "ekran_basligi": str(b.get("ekran_basligi", ""))[:40],
           "youtube": {"baslik": f"Fındık ile Pamuk | {baslik} | 3D Çocuk Çizgi Filmi",
                       "aciklama": f"{b.get('aciklama', '').strip()} Bu bölümün değeri: {deger}.".strip(),
                       "etiketler": ["çocuk çizgi filmi", "3D animasyon", "okul öncesi", "masal", "Fındık ile Pamuk",
                                     "sincap", "tavşan", deger]},
           "cekimler": b.get("cekimler", [])}
    for i, c in enumerate(out["cekimler"]):
        c["id"] = f"c{i + 1}"
        c.setdefault("eylemler", [])
    if b.get("muzik") in ("macera", "normal"):
        out["muzik"] = b["muzik"]
    return out


def _denetle(b, seri, basliklar):
    try:
        h = bolum_denetle.denetle(b, seri)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        return [f"yapı hatası: {type(e).__name__} {e}"]
    if not 5 <= len(b["cekimler"]) <= 7:
        h.append(f"{len(b['cekimler'])} çekim; 5-6 olmalı")
    if not b["baslik"] or b["baslik"].lower() in basliklar:
        h.append("başlık boş ya da önceki bir bölümle aynı")
    if not b["ekran_basligi"]:
        h.append("ekran_basligi boş")
    if set(b.get("baslangic", {})) != {"findik", "pamuk"}:
        h.append("baslangic iki karakteri de içermeli")
    return h


def yaz_bir(no):
    """b{no}.json yazar; başarılıysa yol, değilse None."""
    seri = json.loads((SERI / "seri.json").read_text())
    onceki = [json.loads(p.read_text()) for p in sorted(SERI.glob("bolumler/b*.json"))]
    basliklar = {b["baslik"].lower() for b in onceki}
    kullanilan = [b["deger"] for b in onceki[-15:]]
    deger = random.choice([d for d in DEGERLER if d not in kullanilan] or DEGERLER)
    tur = random.choices(
        ["MACERA/AKSİYON bölümü (koşma, atlama, yarış, keşif; muzik: macera; mekan dere, magara ya da orman)",
         "eğlenceli OYUN/BULMACA bölümü (muzik: macera)",
         "sıcak, komik GÜNLÜK HAYAT bölümü (muzik: normal) ama hareketli ve canlı"], weights=[6, 2, 2])[0]
    istem = ISTEM.format(
        seri_aciklama=seri["aciklama"], tur=tur, deger=deger,
        gecmis="\n".join(f"- {b['baslik']} | {b['deger']}" for b in onceki[-60:]),
        mekanlar=", ".join(f"{k} ({v['aciklama']})" for k, v in seri["mekanlar"].items()),
        nesneler=", ".join(seri["nesneler"]), tipler=", ".join(bolum_denetle.TIPLER),
        hareketler=", ".join(sorted(bolum_denetle.HAREKETLER)), isiklar=", ".join(bolum_denetle.ISIK),
        ifadeler="/".join(bolum_denetle.IFADELER), sx=bolum_denetle.SAHNE_X, sy=bolum_denetle.SAHNE_Y,
        atlayis=bolum_denetle.ATLAYIS, uzanma=bolum_denetle.UZANMA, verme=bolum_denetle.VERME,
        ornekler="\n\n".join(_ornek(a) for a in ORNEKLER if (SERI / "bolumler" / f"{a}.json").exists()))
    ham = gemini.sor(istem, sicaklik=1.0)
    for tur_no in range(DENEME):
        ham = ham if isinstance(ham, dict) else {}
        aciklama = ham.get("aciklama") or aciklama if tur_no else ham.get("aciklama", "")
        b = _tamamla({**ham, "aciklama": aciklama}, no, seri)
        h = _denetle(b, seri, basliklar)
        if not h:  # yapı geçti: çocuk güvenliği / dil denetimi
            metin = "\n".join(f"{s['kim']}: {s['metin']}" for c in b["cekimler"] for s in c["satirlar"])
            v = gemini.sor(DENETIM_ISTEMI.format(senaryo=f"Başlık: {b['baslik']}\n{metin}"), sicaklik=0.1)
            if v.get("uygun") is True:
                yol = SERI / "bolumler" / f"b{no:03d}.json"
                yol.write_text(json.dumps(b, ensure_ascii=False, indent=1))
                print(f"  yazıldı: {yol.name} {b['baslik']} ({b['deger']}, {b['mekan']}, "
                      f"~{bolum_denetle.tahmini_sure(b):.0f} sn)", flush=True)
                return yol
            h = [f"içerik denetimi: {v.get('neden', 'uygun değil')}"]
        print(f"  b{no:03d} düzeltme {tur_no + 1}: {h[:4]}", flush=True)
        if tur_no < DENEME - 1:
            ham = gemini.sor(DUZELT.format(hatalar="\n".join("- " + x for x in h[:15]),
                                           bolum=json.dumps({**{k: v for k, v in b.items() if k != "youtube"}, "aciklama": aciklama},
                                                            ensure_ascii=False)), sicaklik=0.4)
    return None
