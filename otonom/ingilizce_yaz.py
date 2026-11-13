"""Fındık ile Pamuk İngilizce dersleri yazarı (Gemini): müfredattan sıradaki konu -> ders JSON'u (e*.json).

2026-11-13 kullanıcı: günde 1 İngilizce eğitim Shorts'u, İngilizce öğretmeye yönelik. Ders kalıbı ve kurallar
seri/findik-ile-pamuk/ingilizce_yaz1.py'deki elle yazılmış e001-e004 ile aynıdır:
  her kelime: Türkçe durum -> İngilizce kelime (dil: en, anlam: kart) -> anlatıcı Türkçe anlamı + "Sen de söyle!"
  -> İngilizce tekrar + bekle (çocuk tekrar etsin). Son çekim: kelimeler bir arada + Türkçe övgü.
Yapı (cocuk3d.bolum_denetle), ders kuralları (ders_denetle) ve çocuk güvenliği denetiminden geçmeyen yazılmaz.
"""
import json
import re
from pathlib import Path

from cocuk.senaryo import DENETIM_ISTEMI
from cocuk3d import bolum_denetle
from ortak import gemini

DEPO = Path(__file__).resolve().parent.parent
SERI = DEPO / "seri" / "findik-ile-pamuk"
DENEME = 4
ORNEKLER = ["e004", "e002", "e001"]

# (kod, konu, konu_en, [(en, tr)]) — kolaydan zora; nesnesi sahnede olan kelimeler (elma, top, kova, palamut,
# harita, sandık) ve karakterin yapabildiği hareketler/ifadeler görsel olarak da gösterilir.
MUFREDAT = [
    ("renkler_1", "Renkler", "Colors", [("red", "kırmızı"), ("white", "beyaz"), ("orange", "turuncu")]),
    ("duygular", "Duygular", "Feelings", [("happy", "mutlu"), ("sad", "üzgün"), ("surprised", "şaşırmış")]),
    ("hayvanlar_1", "Hayvanlar", "Animals", [("squirrel", "sincap"), ("rabbit", "tavşan"), ("bird", "kuş")]),
    ("sayilar_2", "Sayılar", "Numbers", [("four", "dört"), ("five", "beş"), ("six", "altı")]),
    ("vucut_1", "Vücudumuz", "Body Parts", [("head", "baş"), ("ears", "kulaklar"), ("nose", "burun")]),
    ("zitlar_1", "Zıt Kelimeler", "Opposites", [("big", "büyük"), ("small", "küçük"), ("up", "yukarı")]),
    ("meyveler", "Meyveler", "Fruits", [("apple", "elma"), ("banana", "muz"), ("strawberry", "çilek")]),
    ("renkler_2", "Renkler", "Colors", [("blue", "mavi"), ("yellow", "sarı"), ("green", "yeşil")]),
    ("hareketler_2", "Hareketler", "Action Words", [("sit down", "otur"), ("stand up", "kalk"), ("wave", "el salla")]),
    ("doga", "Doğa", "Nature", [("tree", "ağaç"), ("flower", "çiçek"), ("water", "su")]),
    ("aile", "Ailem", "Family", [("mom", "anne"), ("dad", "baba"), ("baby", "bebek")]),
    ("sayilar_3", "Sayılar", "Numbers", [("seven", "yedi"), ("eight", "sekiz"), ("nine", "dokuz"), ("ten", "on")]),
    ("hava", "Hava Durumu", "Weather", [("sun", "güneş"), ("rain", "yağmur"), ("cloud", "bulut")]),
    ("sekiller", "Şekiller", "Shapes", [("circle", "daire"), ("square", "kare"), ("triangle", "üçgen")]),
    ("nezaket", "Nazik Sözler", "Polite Words", [("please", "lütfen"), ("sorry", "özür dilerim"), ("you're welcome", "rica ederim")]),
    ("oyuncaklar", "Oyuncaklar", "Toys", [("toy", "oyuncak"), ("ball", "top"), ("box", "kutu")]),
    ("yiyecekler", "Yiyecekler", "Food", [("bread", "ekmek"), ("milk", "süt"), ("cake", "pasta")]),
    ("zitlar_2", "Zıt Kelimeler", "Opposites", [("fast", "hızlı"), ("slow", "yavaş"), ("down", "aşağı")]),
    ("vucut_2", "Vücudumuz", "Body Parts", [("hands", "eller"), ("eyes", "gözler"), ("feet", "ayaklar")]),
    ("hayvanlar_2", "Hayvanlar", "Animals", [("cat", "kedi"), ("dog", "köpek"), ("fish", "balık")]),
    ("yonler", "Yönler", "Directions", [("left", "sol"), ("right", "sağ"), ("here", "burada")]),
    ("gunun_zamani", "Günün Zamanları", "Times of Day", [("morning", "sabah"), ("night", "gece"), ("good night", "iyi geceler")]),
    ("kiyafetler", "Kıyafetler", "Clothes", [("hat", "şapka"), ("shoes", "ayakkabı"), ("coat", "mont")]),
    ("renkler_3", "Renkler", "Colors", [("pink", "pembe"), ("brown", "kahverengi"), ("black", "siyah")]),
    ("ev", "Evimiz", "My Home", [("house", "ev"), ("door", "kapı"), ("bed", "yatak")]),
    ("sorular", "Soru Kelimeleri", "Question Words", [("what", "ne"), ("where", "nerede"), ("who", "kim")]),
    ("cumleler_1", "İlk Cümleler", "First Sentences", [("I am happy", "ben mutluyum"), ("I like apples", "elmaları severim"), ("Let's play", "hadi oynayalım")]),
    ("deniz", "Deniz", "The Sea", [("sea", "deniz"), ("sand", "kum"), ("shell", "deniz kabuğu")]),
    ("mevsimler", "Mevsimler", "Seasons", [("winter", "kış"), ("summer", "yaz"), ("snow", "kar")]),
    ("sayilar_tekrar", "Sayılar Tekrarı", "Counting to Ten", [("one", "bir"), ("five", "beş"), ("ten", "on")]),
]

ISTEM = """Sen 3-7 yaş Türk çocuklarına İngilizce öğreten 3D çizgi film "Fındık ile Pamuk"un eğitim senaristisin.
YENİ bir İngilizce ders Shorts'u yaz. Konu: {konu} ({konu_en}). Öğretilecek kelimeler (bu sırayla):
{kelimeler}

Karakterler: findik (Fındık: meraklı, enerjik sincap), pamuk (Pamuk: yumuşak kalpli tavşan), anlatici (yalnız ses).

DERS KALIBI (her kelime için, ayrı bir çekimde):
 1) (isteğe bağlı) kısa Türkçe durum satırı;
 2) İngilizce satır: {{"kim": "findik|pamuk", "dil": "en", "metin": "Red!", "anlam": "kırmızı"}} (kart ekrana çıkar);
 3) anlatici Türkçe: "<türkçe anlamı> demek. Sen de söyle!" (ya da "Hadi söyle!", "Sen de say!");
 4) İngilizce tekrar: {{"kim": ..., "dil": "en", "metin": "Red, red!", "bekle": 1.5}} (çocuk tekrar etsin diye sessiz pay).
İlk çekim: Türkçe merak uyandıran tek satır (ör. "Kırmızı İngilizce ne demek, biliyor musun?").
Son çekim: İngilizce satırda kelimeler bir arada (ör. "Red! White! Orange!") + anlatici Türkçe kısa övgü.
Kelimeyi mümkünse GÖSTER: sahnedeki nesneyi tut, hareketi yap (zipla/kos/yuru/otur/kalk/el_salla), ifadeyi
değiştir (mutlu/uzgun/saskin/kararli); sayılarda o kadar zıpla (kez 1-3).

DİL KURALLARI (otomatik denetlenir):
- "dil": "en" satırı YALNIZ İngilizce (en çok 6 kelime, Türkçe harf/kelime yok, karakter adı yok).
- Türkçe satırlarda hedef İngilizce kelimeler GEÇMEZ (Türkçe ses İngilizceyi yanlış okur).
- Her hedef kelime en az 2 İngilizce satırda geçer; ilk geçtiği satırda "anlam" (Türkçe karşılığı) olur.
- "anlam" yalnız İngilizce satırda; "bekle" 1.0-2.0.
- Türkçe: doğru, sade, sevimli; satır en çok 12 kelime.

SÖZLÜK (yalnız bunlar):
- mekan: {mekanlar}
- nesne: {nesneler} (sandik taşınamaz; nesne_yerlesim: {{"nesne": [x, y, 0.0]}}; bir karakter aynı anda tek nesne tutar)
- çekim tip: {tipler}; hareket: {hareketler}; isik: {isiklar}
- eylemler: yuru/kos/atla {{"nereye": [x, y], "son": 0-1}}, zipla {{"kez": 1-3, "son"}}, el_salla {{"son"}},
  tut {{"nesne"}}, ver {{"nesne", "kime"}}, ac {{"nesne": "sandik"}}, ifade {{"tur": {ifadeler}}},
  bak {{"kime": karakter}} ya da {{"yon": -1..1}}, otur, kalk. Her eylemde "kim" ve "bas" (0-1, çekim içi zaman).
- Sahne: x {sx}, y {sy}. tut: nesneye en çok {uzanma} m (önce yürü). ver: karakterler arası en çok {verme} m.
  Otururken yürüme/zıplama yok (önce kalk). Karakter bir çekimde yürüdüğü yerde kalır.
- 5-6 çekim, toplam süre 30-50 sn. Korku, tehlike, kötü karakter YOK.
- Bir çekimde yürüyen/koşan
  karakter başladığı yere geri dönmesin (hareket görünmez olur).
- "ekran_basligi": en çok 4 kelimelik Türkçe merak sorusu (ör. "Kırmızı İngilizce Ne?").
- "aciklama": ebeveynlere 1-2 cümle (hangi kelimeler öğretiliyor).

ÖRNEK DERSLER (biçim için; içerik kopyalama):
{ornekler}

Yalnızca şu JSON'u döndür:
{{"mekan": "", "muzik": "macera|normal", "baslangic": {{"findik": [x, y], "pamuk": [x, y]}}, "nesne_yerlesim": {{}},
 "ekran_basligi": "", "aciklama": "", "cekimler": [ ... ]}}"""

DUZELT = """Bu İngilizce ders bölümü JSON'u otomatik denetimden geçemedi. Sorunlar:
{hatalar}

Kurallar aynı. Yalnız sorunları düzelt, aynı yapıda TAM JSON döndür.

{bolum}"""


def _ornek(ad):
    b = json.loads((SERI / "bolumler" / f"{ad}.json").read_text())
    return json.dumps({k: b[k] for k in ("konu", "kelimeler", "mekan", "muzik", "baslangic", "nesne_yerlesim",
                                         "ekran_basligi", "cekimler") if k in b}, ensure_ascii=False)


def mevcut():
    return [json.loads(p.read_text()) for p in sorted(SERI.glob("bolumler/e*.json"))]


def siradaki_konu(onceki):
    """Müfredatta en az işlenmiş konu (eşitlikte müfredat sırası)."""
    sayi = {}
    for b in onceki:
        sayi[b.get("konu_kodu")] = sayi.get(b.get("konu_kodu"), 0) + 1
    return min(MUFREDAT, key=lambda m: (sayi.get(m[0], 0), MUFREDAT.index(m)))


def _gecer(kelime, metin):
    return re.search(r"(?<![a-z])" + re.escape(kelime.lower()) + r"(?![a-z])", metin.lower()) is not None


def ders_denetle(b):
    """Öğretim kuralları: her kelime >= 2 İngilizce satırda, ilkinde anlam; Türkçe satırda hedef kelime yok."""
    h = []
    satirlar = [s for c in b["cekimler"] for s in c["satirlar"]]
    en = [s for s in satirlar if s.get("dil") == "en"]
    tr = [s for s in satirlar if s.get("dil", "tr") == "tr"]
    for k in b.get("kelimeler", []):
        gecen = [s for s in en if _gecer(k["en"], s["metin"])]
        if len(gecen) < 2:
            h.append(f"'{k['en']}' en az 2 İngilizce satırda geçmeli ({len(gecen)})")
        elif not gecen[0].get("anlam"):
            h.append(f"'{k['en']}' ilk geçtiği İngilizce satırda anlam (Türkçe karşılığı) yok")
        for s in tr:
            if len(k["en"]) > 2 and _gecer(k["en"], s["metin"]):
                h.append(f"Türkçe satırda İngilizce hedef kelime var ('{k['en']}'): {s['metin']}")
    if not any(s.get("bekle") for s in en):
        h.append("tekrar payı (bekle) olan İngilizce satır yok")
    if not tr or tr[0] is not b["cekimler"][0]["satirlar"][0]:
        h.append("ilk satır Türkçe merak sorusu olmalı")
    return h


def _tamamla(ham, no, konu):
    kod, ad, ad_en, kelimeler = konu
    ham = ham if isinstance(ham, dict) else {}
    kel_metin = ", ".join(e[:1].upper() + e[1:] for e, _ in kelimeler)
    tekrar = sum(1 for b in mevcut() if b.get("konu_kodu") == kod)
    baslik = f"{ad}: {kel_metin}" + (f" ({tekrar + 1}. Tekrar)" if tekrar else "")
    out = {"seri_id": "findik-ile-pamuk", "bolum_no": no, "tur": "ingilizce", "baslik": baslik,
           "deger": "İngilizce öğrenmek", "konu": ad, "konu_en": ad_en, "konu_kodu": kod,
           "kelimeler": [{"en": e, "tr": t} for e, t in kelimeler],
           "giris_metni": f"Fındık ile Pamuk İngilizce öğreniyor! Ders {no}: {ad}.",
           "onceki_olaylar": [], "bu_bolumde_degisen": [], "mekan": ham.get("mekan"),
           "baslangic": ham.get("baslangic", {}), "nesne_yerlesim": ham.get("nesne_yerlesim") or {},
           "ekran_basligi": str(ham.get("ekran_basligi", ""))[:40],
           "youtube": {"aciklama": str(ham.get("aciklama", "")).strip()[:400]},
           "cekimler": ham.get("cekimler", []), "muzik": ham.get("muzik") if ham.get("muzik") in ("macera", "normal") else "normal"}
    for i, c in enumerate(out["cekimler"]):
        c["id"] = f"c{i + 1}"
        c.setdefault("eylemler", [])
    return out


def ders_mekanlari(seri):
    """bahce: geniş düz çimen kalite kontrolünde "boş kare" sayılıyor (2026-11-13 deneme); derslerde yok."""
    from otonom.masal_yaz import uygun_mekanlar
    return {k: v for k, v in uygun_mekanlar(seri).items() if k != "bahce"}


def _denetle(b, seri):
    try:
        h = bolum_denetle.denetle(b, seri) + ders_denetle(b)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        return [f"yapı hatası: {type(e).__name__} {e}"]
    if not 5 <= len(b["cekimler"]) <= 7:
        h.append(f"{len(b['cekimler'])} çekim; 5-6 olmalı")
    if not b["ekran_basligi"]:
        h.append("ekran_basligi boş")
    if b.get("mekan") in seri["mekanlar"] and b["mekan"] not in ders_mekanlari(seri):
        h.append(f"{b['mekan']} mekânı kullanılmaz; şunlardan seç: {', '.join(ders_mekanlari(seri))}")
    if set(b.get("baslangic", {})) != {"findik", "pamuk"}:
        h.append("baslangic iki karakteri de içermeli")
    return h


def yaz_bir(no):
    """e{no}.json yazar; başarılıysa yol, değilse None."""
    seri = json.loads((SERI / "seri.json").read_text())
    konu = siradaki_konu(mevcut())
    istem = ISTEM.format(
        konu=konu[1], konu_en=konu[2], kelimeler="\n".join(f"- {e} = {t}" for e, t in konu[3]),
        mekanlar=", ".join(f"{k} ({v['aciklama']})" for k, v in ders_mekanlari(seri).items()),
        nesneler=", ".join(seri["nesneler"]), tipler=", ".join(bolum_denetle.TIPLER),
        hareketler=", ".join(sorted(bolum_denetle.HAREKETLER)), isiklar=", ".join(bolum_denetle.ISIK),
        ifadeler="/".join(bolum_denetle.IFADELER), sx=bolum_denetle.SAHNE_X, sy=bolum_denetle.SAHNE_Y,
        uzanma=bolum_denetle.UZANMA, verme=bolum_denetle.VERME,
        ornekler="\n\n".join(_ornek(a) for a in ORNEKLER if (SERI / "bolumler" / f"{a}.json").exists()))
    ham = gemini.sor(istem, sicaklik=0.9)
    for tur_no in range(DENEME):
        b = _tamamla(ham, no, konu)
        h = _denetle(b, seri)
        if not h:
            metin = "\n".join(f"{s['kim']}: {s['metin']}" for c in b["cekimler"] for s in c["satirlar"])
            v = gemini.sor(DENETIM_ISTEMI.format(senaryo=f"Başlık: {b['baslik']} (İngilizce dersi)\n{metin}"),
                           sicaklik=0.1)
            if v.get("uygun") is True:
                yol = SERI / "bolumler" / f"e{no:03d}.json"
                yol.write_text(json.dumps(b, ensure_ascii=False, indent=1))
                print(f"  yazıldı: {yol.name} {b['baslik']} (~{bolum_denetle.tahmini_sure(b):.0f} sn)", flush=True)
                return yol
            h = [f"içerik denetimi: {v.get('neden', 'uygun değil')}"]
        print(f"  e{no:03d} düzeltme {tur_no + 1}: {h[:4]}", flush=True)
        if tur_no < DENEME - 1:
            ham = gemini.sor(DUZELT.format(hatalar="\n".join("- " + x for x in h[:15]),
                                           bolum=json.dumps({k: b[k] for k in ("mekan", "muzik", "baslangic",
                                                                               "nesne_yerlesim", "ekran_basligi",
                                                                               "cekimler")} | {"aciklama": b["youtube"]["aciklama"]},
                                                            ensure_ascii=False)), sicaklik=0.4)
    return None
