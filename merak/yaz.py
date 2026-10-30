"""Merak Arşivi senaryo yazarı: kaynak paketinden uzun belgesel + Shorts senaryoları.

Yanlış bilgiye karşı üç kat:
  1) Gemini yalnız verilen Wikipedia metnini kullanır (istem kuralı).
  2) Senaryodaki her sayı (>= 13) kaynak metinde birebir geçmeli (kodla, yapay zekâsız denetim).
  3) Ayrı bir Gemini çağrısı senaryoyu kaynağa karşı cümle cümle denetler; desteklenmeyen iddia = ret.
Hatalar düzeltme için Gemini'ye geri verilir; DENEME kez geçemeyen senaryo yazılmaz.
"""
import json
import random
import re
from pathlib import Path

from merak.grafik import REFERANSLAR
from ortak import gemini

KOK = Path(__file__).resolve().parent
KONULAR = KOK / "konular"
DENEME = 5
KISA_ADET = 4
UZUN_KELIME = (800, 1050)   # ölçüm (Derinkuyu): 0.62 sn/kelime -> ~8.3-10.9 dk
KISA_KELIME = (60, 110)     # Shorts hızında ~0.6 sn/kelime -> ~36-66 sn
YASAK = re.compile(r"\b(intihar|tecavüz|katliam|vahşet|kafa kes|işkence|abone ol|beğen(meyi)? unutma)", re.I)

ORTAK_KURALLAR = """KESİN KURALLAR:
- YALNIZCA aşağıdaki KAYNAK METİN'deki bilgileri kullan. Kaynakta olmayan hiçbir tarih, sayı, isim, iddia ekleme.
- Sayıları RAKAMLA ve kaynakta geçtiği değerle yaz (ör. 1963, 85, 20.000). Birim dönüştürme, yuvarlama yapma.
  Kaynakta tartışmalı/tahmini olan bilgiyi "tahminlere göre", "bazı araştırmacılara göre" diye ver.
- Doğru, akıcı, konuşma diliyle Türkçe; seslendirilecek. Kısaltma, parantez, dipnot, emoji yok.
- Seyirciye hitap edebilirsin ama "abone ol/beğen" deme. Abartılı, yanıltıcı ifade ya da uydurma gizem yok.
- "gorsel": parçanın anlattığına en uygun görsellerin numaraları (aşağıdaki GÖRSEL LİSTESİ'nden).
- "iddialar": senaryodaki her somut bilgi için kaynaktan BİREBİR kopyalanmış kısa alıntı (kaynak_alinti).

ÖZGÜN GRAFİKLER (kanalın kendi görselleri; bir parçaya "grafik" eklenirse o parça boyunca fotoğraf yerine grafik görünür):
- {{"tur": "sayi", "deger": "20.000", "birim": "kişi", "metin": "en çok 8 kelimelik açıklama"}}  -> çarpıcı tek sayı
- {{"tur": "zaman", "olaylar": [{{"yil": "1963", "metin": "en çok 8 kelime"}}]}}  -> 3-5 olaylı zaman çizelgesi
- {{"tur": "karsilastirma", "deger": 85, "birim": "m", "etiket": "kısa ad", "referans": "<anahtar>"}}  -> boy/uzunluk
  karşılaştırması; referans YALNIZ şunlardan, değere yakın olanı seç: {referanslar}
{harita}- Grafikteki her sayı ve yıl da kaynakta birebir geçmeli; grafiği anlatan parçanın metni aynı bilgiyi söylemeli.
- Grafikli parçada da "gorsel" yaz (grafik çizilemezse yedek)."""

UZUN_ISTEM = """Türkçe YouTube belgesel kanalı "Merak Arşivi" için {kelime_alt}-{kelime_ust} kelimelik bir anlatım senaryosu yaz.
Konu: {konu} (çalışma başlığı: {calisma})

Yapı:
- 7-9 bölüm. İlk bölüm (ad: "Giriş") 60-90 kelimelik güçlü bir kanca: en çarpıcı bilgi/soru ile başla.
- Her bölümün 2-4 kelimelik merak uyandıran bir "ad"ı olsun. Son bölüm konuyu bugüne bağlayıp düşündürücü bir cümleyle kapansın.
- Her bölümde 3-7 "parca"; her parça 1-2 cümle, en çok 40 kelime.
- 5-8 parçada "yazi": ekranda büyük görünecek 1-3 kelimelik vurgu (ör. "85 METRE", "MÖ 8. YÜZYIL").
- EN AZ 6 parçada "grafik" (türleri karıştır; bir zaman çizelgesi mutlaka olsun). Grafikler bölümlere yayılsın.
- Anlatım tarzı: {tarz}
- "baslik": YouTube başlığı, en çok 85 karakter, merak uyandırıcı ama dürüst.
- "kapak_yazisi": kapak resmi için en çok 4 kelime, BÜYÜK HARF. "kapak_gorsel": kapak için en çarpıcı görselin numarası.
- "aciklama": YouTube açıklamasının ilk paragrafı, 2-3 cümle. "etiketler": 10-15 Türkçe etiket.

{kurallar}

GÖRSEL LİSTESİ (numara: açıklama):
{gorseller}

KAYNAK METİN:
{kaynak}

Yalnızca şu JSON'u döndür:
{{"baslik": "", "kapak_yazisi": "", "kapak_gorsel": 0, "aciklama": "", "etiketler": [],
 "bolumler": [{{"ad": "Giriş", "parcalar": [{{"metin": "", "gorsel": [0], "yazi": "", "grafik": null}}]}}],
 "iddialar": [{{"iddia": "", "kaynak_alinti": ""}}]}}"""

KISA_ISTEM = """Türkçe YouTube kanalı "Merak Arşivi" için {adet} AYRI dikey Shorts senaryosu yaz. Konu: {konu}
Her Shorts konunun FARKLI bir şaşırtıcı yönünü anlatsın (aynı bilgiyi tekrar etme).

Her Shorts için:
- {kelime_alt}-{kelime_ust} kelime, 5-8 parça; her parça tek cümle, en çok 22 kelime.
- İlk parça ilk 2 saniyede merak uyandıran bir kanca (soru ya da çarpıcı bilgi).
- Son parça kısa bir kapanış; "tüm hikâye kanalda" gibi bir cümle olabilir.
- 1-2 parçada "grafik" (en çarpıcı sayı ya da karşılaştırma).
- "ekran_basligi": ilk saniyelerde ekranda yazacak en çok 5 kelime.
- "baslik": en çok 80 karakter. "aciklama": 1-2 cümle. "etiketler": 6-10 Türkçe etiket.

{kurallar}

GÖRSEL LİSTESİ (numara: açıklama):
{gorseller}

KAYNAK METİN:
{kaynak}

Yalnızca şu JSON'u döndür:
{{"kisalar": [{{"baslik": "", "ekran_basligi": "", "aciklama": "", "etiketler": [],
  "parcalar": [{{"metin": "", "gorsel": [0], "grafik": null}}], "iddialar": [{{"iddia": "", "kaynak_alinti": ""}}]}}]}}"""

TARZLAR = [
    "dedektif gibi: bir soruyla aç, ipuçlarını sırayla ortaya koy, sonunda bilinenle bilinmeyeni ayır",
    "zaman yolculuğu: izleyiciyi o döneme götür ('Yıl ...'), olayları kronolojik anlat",
    "büyük resimden ayrıntıya: önce ölçeği ve önemini göster, sonra parça parça aç",
    "efsane ve gerçek: anlatılanları ve kanıtların söylediğini karşılaştır",
    "bir keşfin hikâyesi: konuyu kimin, nasıl bulduğu/incelediği üzerinden anlat",
]

DUZELT_ISTEM = """Aşağıdaki senaryo JSON'unda şu sorunlar bulundu:
{hatalar}

Yalnızca bu sorunları düzelt (diğer her şeyi koru), aynı JSON yapısını eksiksiz döndür.
Kaynakta olmayan bilgiyi çıkar ya da kaynaktakiyle değiştir.

KAYNAK METİN:
{kaynak}

SENARYO:
{senaryo}"""

DENETIM_ISTEM = """Bir belgesel senaryosunu KAYNAK METİN'e karşı titizlikle denetle.
Senaryodaki her cümleyi incele. Şunları bul:
- kaynakta DESTEKLENMEYEN ya da kaynakla ÇELİŞEN her bilgi (tarih, sayı, isim, olay, nedensellik)
- kaynakta "tahmini/tartışmalı" olup senaryoda kesinmiş gibi verilen iddia
- anlamsız, dil bilgisi hatalı ya da yanıltıcı cümle
Üslup ve süsleme ("karanlık koridorlar" gibi betimleme) sorun değildir; yalnız bilgi doğruluğu ve dil.

KAYNAK METİN:
{kaynak}

SENARYO:
{metin}

JSON döndür: {{"sorunlar": [{{"cumle": "senaryodaki cümle", "neden": "kısa açıklama"}}]}}  (sorun yoksa boş dizi)"""


# ------------------------------------------------------------------ yapay zekâsız denetimler
def _sayi_norm(s):
    s = s.strip(".,")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        return s.replace(".", "").replace(",", "")
    return s.replace(",", ".")


def sayilar(metin):
    return {_sayi_norm(x) for x in re.findall(r"\d[\d.,]*\d|\d", metin)}


def kaynak_metni(paket):
    return (paket["metin_en"] + "\n\n" + paket.get("metin_tr", "")).strip()


def _boslukla(m):
    return re.sub(r"\s+", " ", m).strip().lower()


def sayi_denetimi(metin, kaynak_sayilari):
    """Kaynakta geçmeyen sayılar (12'den büyük; küçük sayılar sıradan sayımlar olabilir)."""
    hatali = []
    for n in sayilar(metin):
        try:
            deger = float(n)
        except ValueError:
            continue
        if deger > 12 and n not in kaynak_sayilari:
            hatali.append(n)
    return hatali


def _parcalar(s):
    if "bolumler" in s:
        return [p for b in s["bolumler"] for p in b.get("parcalar", [])]
    return s.get("parcalar", [])


PARCA_KELIME = 24   # bundan uzun parça cümle sınırlarından bölünür (denetim sınırı uzunda 45, kısada 26)


def _bol(p):
    """Uzun parçayı cümlelerinden bölerek yeni parçalara ayırır; görseller korunur, grafik ilk parçada kalır.
    Kelime ve bilgi değişmez, yalnız "cümle çok uzun" hatası Gemini'ye gitmeden giderilir."""
    if len(p["metin"].split()) <= PARCA_KELIME:
        return [p]
    cumleler = [c for c in re.split(r"(?<=[.!?…])\s+", p["metin"].strip()) if c]
    gruplar, simdiki = [], []
    for c in cumleler:
        if simdiki and len(" ".join(simdiki + [c]).split()) > PARCA_KELIME:
            gruplar.append(simdiki)
            simdiki = []
        simdiki.append(c)
    gruplar.append(simdiki)
    if len(gruplar) == 1:
        return [p]
    return [dict(p, metin=" ".join(g)) if i == 0 else
            {k: v for k, v in p.items() if k not in ("grafik", "yazi", "metin")} | {"metin": " ".join(g)}
            for i, g in enumerate(gruplar)]


def _duzenle(s):
    """Gemini'nin boş (null) ya da yanlış tipli alanlarını denetimden önce düzeltir: denetim çökmez, eksik
    alan hata olarak düzeltmeye gider. JSON nesnesi değilse None."""
    if not isinstance(s, dict):
        return None
    for k in ("baslik", "ekran_basligi", "kapak_yazisi", "aciklama"):
        if k in s and not isinstance(s[k], str):
            s[k] = "" if s[k] is None else str(s[k])

    def parcalar(liste):
        temiz = []
        for p in liste if isinstance(liste, list) else []:
            if not isinstance(p, dict):
                continue
            if not isinstance(p.get("metin"), str):
                p["metin"] = ""
            if not isinstance(p.get("yazi"), str):
                p.pop("yazi", None)
            if not isinstance(p.get("grafik"), dict):
                p.pop("grafik", None)
            temiz.extend(_bol(p))
        return temiz

    if "bolumler" in s:
        s["bolumler"] = [b for b in s["bolumler"] if isinstance(b, dict)] if isinstance(s["bolumler"], list) else []
        for b in s["bolumler"]:
            if not isinstance(b.get("ad"), str):
                b["ad"] = ""
            b["parcalar"] = parcalar(b.get("parcalar"))
    else:
        s["parcalar"] = parcalar(s.get("parcalar"))
    if not isinstance(s.get("iddialar"), list):
        s["iddialar"] = []
    return s


def yapi_denetimi(s, gorsel_sayisi, uzun, kaynak, kaynak_sayilari, koordinat=None):
    h = []
    parcalar = _parcalar(s)
    if not parcalar:
        return ["parça yok"]
    metin = " ".join(p.get("metin", "") for p in parcalar)
    kelime = len(metin.split())
    alt, ust = UZUN_KELIME if uzun else KISA_KELIME
    if not alt <= kelime <= ust:
        hedef = (alt + ust) // 2
        if kelime < alt:
            h.append(f"toplam {kelime} kelime; {alt}-{ust} olmalı: yaklaşık {hedef - kelime} kelime EKLE "
                     "(kaynaktaki başka bilgilerle yeni kısa parçalar ekle; mevcut parçaları uzatma)")
        else:
            h.append(f"toplam {kelime} kelime; {alt}-{ust} olmalı: yaklaşık {kelime - hedef} kelime ÇIKAR "
                     "(en az önemli parçaları sil)")
    if uzun:
        if not 6 <= len(s.get("bolumler", [])) <= 10:
            h.append(f"{len(s.get('bolumler', []))} bölüm; 7-9 olmalı")
        if any(not b.get("ad") or len(b["ad"]) > 32 for b in s.get("bolumler", [])):
            h.append("bölüm adı boş ya da 32 karakterden uzun")
        if not s.get("kapak_yazisi") or len(s["kapak_yazisi"].split()) > 5:
            h.append("kapak_yazisi boş ya da 5 kelimeden uzun")
        if not isinstance(s.get("kapak_gorsel"), int) or not 0 <= s["kapak_gorsel"] < gorsel_sayisi:
            h.append("kapak_gorsel geçersiz numara")
    else:
        if not 4 <= len(parcalar) <= 9:
            h.append(f"{len(parcalar)} parça; 5-8 olmalı")
        if not s.get("ekran_basligi") or len(s["ekran_basligi"].split()) > 6:
            h.append("ekran_basligi boş ya da 6 kelimeden uzun")
    if not s.get("baslik") or len(s["baslik"]) > (90 if uzun else 85):
        h.append("başlık boş ya da çok uzun")
    for i, p in enumerate(parcalar):
        if len(p.get("metin", "").split()) > (45 if uzun else 26):
            h.append(f"parça {i}: cümle çok uzun")
        g = p.get("gorsel")
        if not isinstance(g, list) or not g or any(not isinstance(x, int) or not 0 <= x < gorsel_sayisi for x in g):
            h.append(f"parça {i}: gorsel numaraları geçersiz {g}")
        if re.search(r"[()\[\]*#]|https?:", p.get("metin", "")):
            h.append(f"parça {i}: seslendirilemeyecek işaret/bağlantı var")
    grafikler = [p["grafik"] for p in parcalar if isinstance(p.get("grafik"), dict)]
    if len(grafikler) < (6 if uzun else 1):
        h.append(f"{len(grafikler)} grafik; {'en az 6' if uzun else 'en az 1'} olmalı")
    if uzun and not any(g.get("tur") == "zaman" for g in grafikler):
        h.append("zaman çizelgesi grafiği yok")
    grafik_metni = []
    for g in grafikler:
        tur = g.get("tur")
        if tur not in ("sayi", "zaman", "karsilastirma", "harita"):
            h.append(f"bilinmeyen grafik türü: {tur}")
        elif tur == "harita" and not koordinat:
            h.append("bu konuda harita grafiği kullanılamaz (konum yok)")
        elif tur == "karsilastirma" and (g.get("referans") not in REFERANSLAR
                                         or not re.fullmatch(r"\d+([.,]\d+)?", str(g.get("deger", "")))):
            h.append(f"karşılaştırma referansı/değeri geçersiz: {g.get('referans')} {g.get('deger')}")
        elif tur == "zaman" and not 3 <= len(g.get("olaylar", [])) <= 5:
            h.append("zaman çizelgesi 3-5 olay olmalı")
        elif tur == "sayi" and not str(g.get("deger", "")).strip():
            h.append("sayı grafiğinde değer yok")
        grafik_metni.append(json.dumps(g, ensure_ascii=False))
    eksik_g = sayi_denetimi(" ".join(grafik_metni), kaynak_sayilari)
    if eksik_g:
        h.append(f"grafiklerde kaynakta geçmeyen sayılar: {', '.join(sorted(eksik_g))}")
    if YASAK.search(metin + " " + s.get("baslik", "")):
        h.append("yasaklı ifade")
    eksik = sayi_denetimi(metin + " " + " ".join(p.get("yazi", "") for p in parcalar), kaynak_sayilari)
    if eksik:
        h.append(f"kaynakta geçmeyen sayılar: {', '.join(sorted(eksik))} (kaynaktaki değeri kullan ya da çıkar)")
    kaynak_b = _boslukla(kaynak)
    iddialar = [i for i in s.get("iddialar", []) if isinstance(i, dict) and i.get("kaynak_alinti")]
    tutan = [i for i in iddialar if _boslukla(i["kaynak_alinti"])[:120] in kaynak_b]
    if len(iddialar) < (8 if uzun else 3):
        h.append("iddialar listesi yetersiz (her somut bilgi için kaynaktan alıntı)")
    elif len(tutan) < 0.8 * len(iddialar):
        h.append("iddiaların alıntıları kaynakta birebir bulunamadı: "
                 + "; ".join(i["kaynak_alinti"][:60] for i in iddialar if i not in tutan)[:600])
    return h


def gorsel_listesi(gorseller):
    return "\n".join(f"{i}: {g['baslik'][5:][:70]} — {g['aciklama'][:110]}" for i, g in enumerate(gorseller))


def _ai_denetim(s, kaynak):
    metin = "\n".join(p["metin"] for p in _parcalar(s))
    sonuc = gemini.sor(DENETIM_ISTEM.format(kaynak=kaynak[:60000], metin=metin), sicaklik=0.1)
    sorunlar = sonuc.get("sorunlar", []) if isinstance(sonuc, dict) else []
    return [f"'{str(x.get('cumle') or '')[:90]}': {x.get('neden') or ''}" for x in sorunlar
            if isinstance(x, dict)]


def _dogrula_duzelt(s, gorseller, uzun, kaynak, kaynak_sayilari, koordinat=None):
    """Yapı + sayı + yapay zekâ denetimi; hata varsa Gemini'ye düzelttir. Geçen senaryo ya da None."""
    for tur in range(DENEME):
        s = _duzenle(s)
        if s is None:
            return None
        try:
            h = yapi_denetimi(s, len(gorseller), uzun, kaynak, kaynak_sayilari, koordinat)
        except (TypeError, AttributeError, KeyError, ValueError) as e:
            h = [f"JSON yapısı şemaya uymuyor ({e}); şemadaki alanları eksiksiz ve doğru tipte doldur"]
        if not h:
            h = _ai_denetim(s, kaynak)
        if not h:
            return s
        print(f"    düzeltme {tur + 1}: {h[:4]}", flush=True)
        if tur == DENEME - 1:
            break
        s = gemini.sor(DUZELT_ISTEM.format(hatalar="\n".join("- " + x for x in h), kaynak=kaynak[:60000],
                                           senaryo=json.dumps(s, ensure_ascii=False)), sicaklik=0.3)
    return None


def yaz(kid):
    """Konu klasörüne uzun.json ve kisa1..N.json yazar. Uzun senaryo geçemezse konu 'reddedildi' işaretlenir."""
    d = KONULAR / kid
    paket = json.loads((d / "kaynak.json").read_text())
    gorseller = json.loads((d / "gorseller.json").read_text())
    kaynak = kaynak_metni(paket)
    kaynak_sayilari = sayilar(kaynak)
    koordinat = paket.get("koordinat")
    kurallar = ORTAK_KURALLAR.format(
        referanslar=", ".join(f"{k} ({ad} {v:g} m)" for k, (ad, v) in REFERANSLAR.items()),
        harita=('- {"tur": "harita", "etiket": "yer adı"}  -> dünyadan konuma yakınlaşan harita (giriş bölümünde kullan)\n'
                if koordinat else ""))
    ortak = dict(konu=paket["wiki"], calisma=paket.get("calisma_basligi", ""), kurallar=kurallar,
                 gorseller=gorsel_listesi(gorseller), kaynak=kaynak[:60000])
    if not (d / "uzun.json").exists():
        print(f"  uzun senaryo: {kid}", flush=True)
        s = gemini.sor(UZUN_ISTEM.format(kelime_alt=UZUN_KELIME[0] + 50, kelime_ust=UZUN_KELIME[1] - 50,
                                         tarz=random.choice(TARZLAR), **ortak), sicaklik=0.8)
        s = _dogrula_duzelt(s, gorseller, True, kaynak, kaynak_sayilari, koordinat)
        if not s:
            (d / "reddedildi").write_text("uzun senaryo denetimi geçemedi\n")
            return False
        s["kaynaklar"] = paket["kaynaklar"]
        (d / "uzun.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
    if not list(d.glob("kisa*.json")):
        print(f"  Shorts senaryoları: {kid}", flush=True)
        v = gemini.sor(KISA_ISTEM.format(adet=KISA_ADET, kelime_alt=KISA_KELIME[0] + 5,
                                         kelime_ust=KISA_KELIME[1] - 15, **ortak), sicaklik=0.9)
        kisalar = v.get("kisalar", []) if isinstance(v, dict) else v
        n = 0
        for k in kisalar[:KISA_ADET]:
            k = _dogrula_duzelt(k, gorseller, False, kaynak, kaynak_sayilari, koordinat)
            if k:
                n += 1
                k["kaynaklar"] = paket["kaynaklar"]
                (d / f"kisa{n}.json").write_text(json.dumps(k, ensure_ascii=False, indent=1))
        print(f"  {n} Shorts senaryosu geçti", flush=True)
    return True
