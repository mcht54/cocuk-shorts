"""Merak Arşivi senaryo yazarı: kaynak paketinden uzun belgesel + Shorts senaryoları.

Yanlış bilgiye karşı üç kat:
  1) Gemini yalnız verilen Wikipedia metnini kullanır (istem kuralı).
  2) Senaryodaki her sayı (>= 13) kaynak metinde birebir geçmeli (kodla, yapay zekâsız denetim).
  3) Ayrı bir Gemini çağrısı senaryoyu kaynağa karşı cümle cümle denetler; desteklenmeyen iddia = ret.
Hatalar düzeltme için Gemini'ye geri verilir; DENEME kez geçemeyen senaryo yazılmaz.
Uzun belgesel önce plan (bölümler + grafikler), sonra bölüm bölüm yazılır: her bölümün kelime aralığı küçük
olduğu için tutturulur, toplam da kendiliğinden UZUN_KELIME içinde kalır. Uzun cümle bölme ve eksik görsel
numarası gibi mekanik düzeltmeler Gemini'ye gitmeden kodla yapılır.
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
KISA_KELIME = (45, 110)     # Shorts hızında ~0.6 sn/kelime -> ~27-66 sn
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

PLAN_ISTEM = """Türkçe YouTube belgesel kanalı "Merak Arşivi" için yaklaşık 9 dakikalık bir belgeselin PLANINI çıkar.
Konu: {konu} (çalışma başlığı: {calisma})
Anlatım tarzı: {tarz}

- 8 bölüm. İlk bölümün adı "Giriş" (en çarpıcı bilgi/soru ile kanca); son bölüm konuyu bugüne bağlar.
- Her bölüm için "ad" (2-4 kelime, merak uyandırıcı) ve "anlatilacak": o bölümde anlatılacak, KAYNAKTAKİ somut
  bilgilerin listesi (4-6 madde). Bölümler birbirini TEKRAR ETMESİN; kaynağın farklı yönlerini kapsasın.
- Bölümlerin EN AZ 6'sına bir "grafik" koy (türleri karıştır, biri mutlaka "zaman"); grafiği olmayan bölümde null.
- "baslik": YouTube başlığı, en çok 85 karakter, merak uyandırıcı ama dürüst.
- "kapak_yazisi": en çok 4 kelime, BÜYÜK HARF. "kapak_gorsel": kapak için en çarpıcı görselin numarası.
- "aciklama": YouTube açıklamasının ilk paragrafı, 2-3 cümle. "etiketler": 10-15 Türkçe etiket.

{kurallar}

GÖRSEL LİSTESİ (numara: açıklama):
{gorseller}

KAYNAK METİN:
{kaynak}

Yalnızca şu JSON'u döndür:
{{"baslik": "", "kapak_yazisi": "", "kapak_gorsel": 0, "aciklama": "", "etiketler": [],
 "bolumler": [{{"ad": "Giriş", "anlatilacak": [""], "grafik": null}}]}}"""

BOLUM_ISTEM = """"Merak Arşivi" belgeselinin ({konu}) {no}. bölümünü yaz: "{ad}".
UZUNLUK: TAM OLARAK {alt}-{ust} kelime (bu çok önemli; yaklaşık {hedef} kelime hedefle).
{n_parca} parça; her parça 1-2 kısa cümle (en çok 24 kelime). Anlatım tarzı: {tarz}

Bu bölümde anlatılacaklar: {anlatilacak}
{grafik_notu}
Belgeselin tüm bölümleri (TEKRAR ETME, yalnız bu bölümü yaz): {plan}
Önceki bölümlerin metni (akışı sürdür, aynı bilgiyi yineleme):
{onceki}

{kurallar}

GÖRSEL LİSTESİ (numara: açıklama):
{gorseller}

KAYNAK METİN:
{kaynak}

Yalnızca şu JSON'u döndür:
{{"parcalar": [{{"metin": "", "gorsel": [0], "yazi": "", "grafik": false}}],
 "iddialar": [{{"iddia": "", "kaynak_alinti": "kaynaktan birebir kısa alıntı"}}]}}
("yazi": isteğe bağlı, ekranda büyük görünecek 1-3 kelimelik vurgu; bölümde en çok 1 tane.)"""

BOLUM_DUZELT_ISTEM = """Belgeselin "{ad}" bölümünde şu sorunlar var:
{hatalar}

Yalnız bu sorunları düzelt, aynı JSON yapısını eksiksiz döndür. UZUNLUK {alt}-{ust} kelime olmalı.
Kaynakta olmayan bilgiyi çıkar ya da kaynaktakiyle değiştir.

KAYNAK METİN:
{kaynak}

BÖLÜM:
{bolum}"""

TARZLAR = [
    "dedektif gibi: bir soruyla aç, ipuçlarını sırayla ortaya koy, sonunda bilinenle bilinmeyeni ayır",
    "zaman yolculuğu: izleyiciyi o döneme götür ('Yıl ...'), olayları kronolojik anlat",
    "büyük resimden ayrıntıya: önce ölçeği ve önemini göster, sonra parça parça aç",
    # "efsane ve gerçek" tarzı kaldırıldı (2026-10-30): kaynakta olmayan "efsanelere göre" iddiaları üretiyordu
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


def _kelimeler(m):
    return re.findall(r"\w+", m.lower())


def alinti_var(alinti, kaynak_dortluler):
    """Alıntı kaynakta geçiyor mu: kelime dörtlülerinin en az %60'ı kaynakta (noktalama/ufak farklara dayanıklı)."""
    kumesi, duz = kaynak_dortluler
    k = _kelimeler(alinti)
    if len(k) < 4:  # çok kısa alıntı: kelime sınırlarıyla birebir aranır
        return bool(k) and f" {' '.join(k)} " in duz
    d = [tuple(k[i:i + 4]) for i in range(len(k) - 3)]
    return sum(x in kumesi for x in d) >= 0.6 * len(d)


def dortluler(kaynak):
    k = _kelimeler(kaynak)
    return {tuple(k[i:i + 4]) for i in range(len(k) - 3)}, f" {' '.join(k)} "


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


def grafik_hatasi(g, koordinat=None, kaynak_sayilari=None):
    """Tek grafik tanımının hatası (yoksa None). kaynak_sayilari verilirse sayılar da kaynağa karşı denetlenir."""
    if not isinstance(g, dict):
        return "grafik tanımı nesne değil"
    tur = g.get("tur")
    if tur not in ("sayi", "zaman", "karsilastirma", "harita"):
        return f"bilinmeyen grafik türü: {tur}"
    if tur == "harita" and not koordinat:
        return "bu konuda harita grafiği kullanılamaz (konum yok)"
    if tur == "karsilastirma" and (g.get("referans") not in REFERANSLAR
                                   or not re.fullmatch(r"\d+([.,]\d+)?", str(g.get("deger", "")))):
        return f"karşılaştırma referansı/değeri geçersiz: {g.get('referans')} {g.get('deger')}"
    if tur == "zaman" and (not isinstance(g.get("olaylar"), list) or not 3 <= len(g["olaylar"]) <= 5):
        return "zaman çizelgesi 3-5 olay olmalı"
    if tur == "sayi" and not str(g.get("deger", "")).strip():
        return "sayı grafiğinde değer yok"
    if kaynak_sayilari is not None:
        eksik = sayi_denetimi(json.dumps(g, ensure_ascii=False), kaynak_sayilari)
        if eksik:
            return f"grafikte kaynakta geçmeyen sayılar: {', '.join(sorted(eksik))}"
    return None


def grafik_onar(g, kaynak_sayilari):
    """Onarılabilir grafik hatası kodla düzeltilir: zaman çizelgesinden kaynakta olmayan yıllı olaylar atılır, 5'e kırpılır."""
    if isinstance(g, dict) and g.get("tur") == "zaman" and isinstance(g.get("olaylar"), list):
        g["olaylar"] = [o for o in g["olaylar"] if isinstance(o, dict)
                        and not sayi_denetimi(json.dumps(o, ensure_ascii=False), kaynak_sayilari)][:5]
    return g


def otomatik_grafik(s, kaynak_sayilari, koordinat=None):
    """Shorts'ta geçerli grafik yoksa metindeki kaynakta geçen en büyük sayıdan sayaç grafiği kurar (Gemini'siz).
    Sayı yoksa ve konum biliniyorsa ilk parçaya harita konur."""
    parcalar = _parcalar(s)
    for p in parcalar:
        if p.get("grafik") is not None:
            grafik_onar(p["grafik"], kaynak_sayilari)
            if grafik_hatasi(p["grafik"], koordinat, kaynak_sayilari):
                p.pop("grafik")
    if any(p.get("grafik") for p in parcalar):
        return s
    adaylar = []
    for p in parcalar:
        for m in re.finditer(r"(\d[\d.,]*\d|\d+)\s*([^\W\d_]+)?", p["metin"]):
            n = _sayi_norm(m.group(1))
            try:
                deger = float(n)
            except ValueError:
                continue
            if deger > 12 and n in kaynak_sayilari and not 1000 <= deger <= 2100:  # yıl değil, miktar
                adaylar.append((deger, p, m.group(1).strip(".,"), m.group(2) or ""))
    if adaylar:
        _, p, yazim, birim = max(adaylar, key=lambda x: x[0])
        p["grafik"] = {"tur": "sayi", "deger": yazim, "birim": birim}
    elif koordinat and parcalar:
        parcalar[0]["grafik"] = {"tur": "harita", "etiket": s.get("ekran_basligi", "")[:30]}
    return s


def gorsel_onar(s, gorsel_sayisi):
    """Eksik/geçersiz görsel numaralarını kodla tamamlar (en az kullanılan görsel); Gemini'ye gitmez."""
    parcalar = _parcalar(s)
    kullanim = {i: 0 for i in range(gorsel_sayisi)}
    for p in parcalar:
        if isinstance(p.get("gorsel"), list):
            p["gorsel"] = [x for x in p["gorsel"] if isinstance(x, int) and 0 <= x < gorsel_sayisi]
        else:
            p["gorsel"] = []
        for x in p["gorsel"]:
            kullanim[x] += 1
    for p in parcalar:
        if not p["gorsel"] and kullanim:
            x = min(kullanim, key=lambda k: (kullanim[k], k))
            p["gorsel"] = [x]
            kullanim[x] += 1
    if "kapak_gorsel" in s and not (isinstance(s["kapak_gorsel"], int) and 0 <= s["kapak_gorsel"] < gorsel_sayisi):
        s["kapak_gorsel"] = 0
    return s


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
        hata = grafik_hatasi(g, koordinat)
        if hata:
            h.append(hata)
        grafik_metni.append(json.dumps(g, ensure_ascii=False))
    eksik_g = sayi_denetimi(" ".join(grafik_metni), kaynak_sayilari)
    if eksik_g:
        h.append(f"grafiklerde kaynakta geçmeyen sayılar: {', '.join(sorted(eksik_g))}")
    if YASAK.search(metin + " " + s.get("baslik", "")):
        h.append("yasaklı ifade")
    eksik = sayi_denetimi(metin + " " + " ".join(p.get("yazi", "") for p in parcalar), kaynak_sayilari)
    if eksik:
        h.append(f"kaynakta geçmeyen sayılar: {', '.join(sorted(eksik))} (kaynaktaki değeri kullan ya da çıkar)")
    kaynak_d = dortluler(kaynak)
    iddialar = [i for i in s.get("iddialar", []) if isinstance(i, dict) and isinstance(i.get("kaynak_alinti"), str)]
    tutan = [i for i in iddialar if alinti_var(i["kaynak_alinti"], kaynak_d)]
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
        gorsel_onar(s, len(gorseller))
        if not uzun:
            otomatik_grafik(s, kaynak_sayilari, koordinat)
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


# ------------------------------------------------------------------ uzun belgesel: plan + bölüm bölüm
UZUN_HEDEF = 925
GIRIS_KELIME = (70, 90)


def bolum_araligi(bolum_sayisi, no):
    """Bölüm başına kelime aralığı; tüm bölümler aralık içindeyse toplam UZUN_KELIME içinde kalır."""
    if no == 0:
        return GIRIS_KELIME
    hedef = (UZUN_HEDEF - sum(GIRIS_KELIME) / 2) / (bolum_sayisi - 1)
    return round(hedef * 0.88), round(hedef * 1.12)


def plan_denetimi(plan, gorsel_sayisi, koordinat, kaynak_sayilari):
    """Hatalı grafikleri kodla çıkarır; kalan sorunları döner."""
    h = []
    bolumler = plan.get("bolumler") if isinstance(plan.get("bolumler"), list) else []
    bolumler = plan["bolumler"] = [b for b in bolumler if isinstance(b, dict)]
    if not 7 <= len(bolumler) <= 9:
        h.append(f"{len(bolumler)} bölüm; 8 olmalı")
    for b in bolumler:
        if not isinstance(b.get("ad"), str) or not b["ad"].strip() or len(b["ad"]) > 32:
            h.append("bölüm adı boş ya da 32 karakterden uzun")
        if not isinstance(b.get("anlatilacak"), list) or not b["anlatilacak"]:
            h.append(f"'{b.get('ad')}' bölümünde anlatilacak listesi yok")
        if b.get("grafik") is not None and grafik_hatasi(grafik_onar(b["grafik"], kaynak_sayilari), koordinat,
                                                         kaynak_sayilari):
            b["grafik"] = None
    grafikler = [b["grafik"] for b in bolumler if b.get("grafik")]
    if len(grafikler) < 6:
        h.append(f"{len(grafikler)} geçerli grafik; en az 6 bölümde geçerli grafik olmalı (sayılar kaynakta birebir)")
    if not any(g.get("tur") == "zaman" for g in grafikler):
        h.append("zaman çizelgesi grafiği yok (3-5 olay, yıllar kaynakta birebir)")
    for k, ust in (("baslik", 85), ("kapak_yazisi", 40)):
        if not isinstance(plan.get(k), str) or not plan[k].strip() or len(plan[k]) > ust:
            h.append(f"{k} boş ya da çok uzun")
    if isinstance(plan.get("kapak_yazisi"), str) and len(plan["kapak_yazisi"].split()) > 5:
        h.append("kapak_yazisi en çok 4 kelime olmalı")
    if not isinstance(plan.get("kapak_gorsel"), int) or not 0 <= plan["kapak_gorsel"] < gorsel_sayisi:
        plan["kapak_gorsel"] = 0
    return h


BOLUM_TOLERANS = 0.9   # bölüm alt sınırın %90'ına kadar kabul; toplam kısa kalırsa sonda tamamlanır


def bolum_denetimi(b, alt, ust, kaynak, kaynak_sayilari):
    h = []
    kelime = len(" ".join(p["metin"] for p in b["parcalar"]).split())
    if kelime < alt * BOLUM_TOLERANS:
        h.append(f"{kelime} kelime; {alt}-{ust} olmalı: yaklaşık {(alt + ust) // 2 - kelime} kelime EKLE "
                 "(kaynaktaki bu bölüme ait başka bilgilerle yeni kısa parçalar)")
    elif kelime > ust:
        h.append(f"{kelime} kelime; {alt}-{ust} olmalı: yaklaşık {kelime - (alt + ust) // 2} kelime ÇIKAR")
    metin = " ".join(p["metin"] + " " + p.get("yazi", "") for p in b["parcalar"])
    eksik = sayi_denetimi(metin, kaynak_sayilari)
    if eksik:
        h.append(f"kaynakta geçmeyen sayılar: {', '.join(sorted(eksik))} (kaynaktaki değeri kullan ya da çıkar)")
    if YASAK.search(metin):
        h.append("yasaklı ifade")
    for i, p in enumerate(b["parcalar"]):
        if re.search(r"[()\[\]*#]|https?:", p["metin"]):
            h.append(f"parça {i}: seslendirilemeyecek işaret/bağlantı var")
        if len(p["metin"].split()) > 40:
            h.append(f"parça {i}: cümle çok uzun (en çok 24 kelimelik cümleler yaz)")
    # kaynakta bulunmayan alıntılar atılır (doğruluk asıl sayı + yapay zekâ denetimiyle); en az biri tutmalı
    kaynak_d = dortluler(kaynak)
    b["iddialar"] = [i for i in b.get("iddialar", []) if isinstance(i, dict)
                     and isinstance(i.get("kaynak_alinti"), str) and alinti_var(i["kaynak_alinti"], kaynak_d)]
    if not b["iddialar"]:
        h.append("iddialar: kaynaktan kelimesi kelimesine kopyalanmış alıntı yok (İngilizce kaynaktan birebir kopyala)")
    return h


ISARET = {"tur": "_isaret"}


def _grafik_yerlestir(b, grafik):
    """Plan grafiğini Gemini'nin işaretlediği (yoksa değeri geçen, yoksa ilk) parçaya koyar; başka grafik bırakmaz."""
    isaretli = [p for p in b["parcalar"] if p.get("grafik") == ISARET]
    for p in b["parcalar"]:
        p.pop("grafik", None)
    if not grafik or not b["parcalar"]:
        return
    deger = str(grafik.get("deger", ""))
    (isaretli or [p for p in b["parcalar"] if deger and deger in p["metin"]] or b["parcalar"])[0]["grafik"] = grafik


def _bolum_hazirla(ham, gorsel_sayisi):
    """Gemini bölüm yanıtını temizler: grafik işareti korunur (uzun parça bölünse de ilk parçada kalır)."""
    if isinstance(ham, list):  # bazı modeller yalnız parça listesini döndürür
        ham = {"parcalar": ham}
    if isinstance(ham, dict) and not isinstance(ham.get("parcalar"), list):  # {"bolum": {...}} sarmalı
        ic = [v for v in ham.values() if isinstance(v, dict) and isinstance(v.get("parcalar"), list)]
        ham = ic[0] if ic else ham
    if not isinstance(ham, dict) or not isinstance(ham.get("parcalar"), list):
        return None
    parcalar = [dict(p, grafik=dict(ISARET)) if isinstance(p, dict) and p.get("grafik") is True else p
                for p in ham["parcalar"]]
    b = _duzenle({"parcalar": parcalar, "iddialar": ham.get("iddialar")})
    if not b["parcalar"]:
        return None
    return gorsel_onar(b, gorsel_sayisi)


EK_ISTEM = """Belgeselin "{ad}" bölümü {eksik} kelime kısa. Bu bölüme, KAYNAK METİN'den henüz anlatılmamış bilgilerle
yaklaşık {eksik} kelimelik 2-3 YENİ parça yaz (her parça 1-2 kısa cümle). Mevcut parçaları TEKRARLAMA.
Mevcut bölüm: {mevcut}

{kurallar}

GÖRSEL LİSTESİ (numara: açıklama):
{gorseller}

KAYNAK METİN:
{kaynak}

Yalnızca YENİ parçaları döndür: {{"parcalar": [{{"metin": "", "gorsel": [0]}}],
 "iddialar": [{{"iddia": "", "kaynak_alinti": "kaynaktan birebir kısa alıntı"}}]}}"""


def _kelime(b):
    return len(" ".join(p["metin"] for p in b["parcalar"]).split())


def kirp(b, ust):
    """Uzun bölümü kodla kısaltır: sondan (ilk ve grafikli parça hariç) parça atar. Gemini'ye gitmez."""
    while _kelime(b) > ust:
        adaylar = [i for i in range(len(b["parcalar"]) - 1, 0, -1) if not b["parcalar"][i].get("grafik")]
        if not adaylar or _kelime(b) - len(b["parcalar"][adaylar[0]]["metin"].split()) < 0.85 * ust:
            break
        b["parcalar"].pop(adaylar[0])
    return b


def _bolum_yaz(no, plan, ortak, gorseller, kaynak, kaynak_sayilari, tarz, onceki):
    pb = plan["bolumler"][no]
    alt, ust = bolum_araligi(len(plan["bolumler"]), no)
    grafik = pb.get("grafik")
    grafik_notu = (f'Bu bölümün grafiği: {json.dumps(grafik, ensure_ascii=False)} — bu bilgiyi anlatan parçaya '
                   '"grafik": true yaz (tek parça).' if grafik else "")
    istem = BOLUM_ISTEM.format(konu=ortak["konu"], no=no + 1, ad=pb["ad"], alt=alt, ust=ust, hedef=(alt + ust) // 2,
                               n_parca=f"{max(3, alt // 20)}-{max(4, ust // 14)}", tarz=tarz,
                               anlatilacak="; ".join(map(str, pb.get("anlatilacak", []))), grafik_notu=grafik_notu,
                               plan=" | ".join(f"{i + 1}. {x['ad']}" for i, x in enumerate(plan["bolumler"])),
                               onceki=onceki[-6000:] or "(ilk bölüm)", kurallar=ortak["kurallar"],
                               gorseller=ortak["gorseller"], kaynak=ortak["kaynak"])
    ham = gemini.sor(istem, sicaklik=0.8)
    for tur in range(DENEME):
        b = _bolum_hazirla(ham, len(gorseller))
        if b is None:
            h = ["JSON yapısı şemaya uymuyor; parcalar listesi boş ya da hatalı"]
        else:
            _grafik_yerlestir(b, grafik)
            kirp(b, ust)
            if _kelime(b) < alt:  # kısa: yalnız yeni parça iste, mevcutlara ekle
                ek = gemini.sor(EK_ISTEM.format(ad=pb["ad"], eksik=(alt + ust) // 2 - _kelime(b),
                                                mevcut=" ".join(p["metin"] for p in b["parcalar"]),
                                                kurallar=ortak["kurallar"], gorseller=ortak["gorseller"],
                                                kaynak=ortak["kaynak"]), sicaklik=0.7)
                ek = _bolum_hazirla(ek, len(gorseller))
                if ek:
                    for p in ek["parcalar"]:
                        p.pop("grafik", None)
                    b["parcalar"] += ek["parcalar"]
                    b["iddialar"] += ek["iddialar"]
                    kirp(b, ust)
            h = bolum_denetimi(b, alt, ust, kaynak, kaynak_sayilari)
            if not h:
                h = _ai_denetim(b, kaynak)
            if not h:
                return {"ad": pb["ad"], "parcalar": b["parcalar"], "iddialar": b["iddialar"]}
        print(f"    bölüm {no + 1} düzeltme {tur + 1}: {h[:3]}", flush=True)
        if tur == DENEME - 1:
            break
        mevcut = ({"parcalar": [dict(p, grafik=True) if p.get("grafik") else p for p in b["parcalar"]],
                   "iddialar": b["iddialar"]} if b else ham)
        ham = gemini.sor(BOLUM_DUZELT_ISTEM.format(ad=pb["ad"], hatalar="\n".join("- " + x for x in h), alt=alt,
                                                   ust=ust, kaynak=ortak["kaynak"],
                                                   bolum=json.dumps(mevcut, ensure_ascii=False)), sicaklik=0.3)
    return None


def uzun_yaz(ortak, gorseller, kaynak, kaynak_sayilari, koordinat):
    """Plan + bölüm bölüm yazım. Geçen tam senaryo ya da None."""
    tarz = random.choice(TARZLAR)
    plan = gemini.sor(PLAN_ISTEM.format(tarz=tarz, **ortak), sicaklik=0.8)
    for tur in range(DENEME):
        plan = plan if isinstance(plan, dict) else {}
        h = plan_denetimi(plan, len(gorseller), koordinat, kaynak_sayilari)
        if not h:
            break
        print(f"    plan düzeltme {tur + 1}: {h[:3]}", flush=True)
        if tur == DENEME - 1:
            return None
        plan = gemini.sor(DUZELT_ISTEM.format(hatalar="\n".join("- " + x for x in h), kaynak=ortak["kaynak"],
                                              senaryo=json.dumps(plan, ensure_ascii=False)), sicaklik=0.3)
    bolumler, onceki = [], ""
    for no in range(len(plan["bolumler"])):
        b = _bolum_yaz(no, plan, ortak, gorseller, kaynak, kaynak_sayilari, tarz, onceki)
        if not b:
            print(f"    bölüm {no + 1} geçemedi", flush=True)
            return None
        bolumler.append(b)
        onceki += f"\n[{b['ad']}] " + " ".join(p["metin"] for p in b["parcalar"])
    for _ in range(3):  # bölüm toleransı yüzünden toplam kısa kaldıysa en kısa bölüme denetimli ek parça
        toplam = sum(_kelime(b) for b in bolumler)
        if toplam >= UZUN_KELIME[0]:
            break
        b = min(bolumler[1:], key=_kelime)
        ek = _bolum_hazirla(gemini.sor(EK_ISTEM.format(
            ad=b["ad"], eksik=UZUN_KELIME[0] + 40 - toplam, mevcut=" ".join(p["metin"] for p in b["parcalar"]),
            kurallar=ortak["kurallar"], gorseller=ortak["gorseller"], kaynak=ortak["kaynak"]), sicaklik=0.7),
            len(gorseller))
        if ek and not bolum_denetimi(ek, 0, 10 ** 6, kaynak, kaynak_sayilari) and not _ai_denetim(ek, kaynak):
            for p in ek["parcalar"]:
                p.pop("grafik", None)
            b["parcalar"] += ek["parcalar"]
            b["iddialar"] += ek["iddialar"]
    s = {k: plan.get(k) for k in ("baslik", "kapak_yazisi", "kapak_gorsel", "aciklama", "etiketler")}
    s["bolumler"] = [{"ad": b["ad"], "parcalar": b["parcalar"]} for b in bolumler]
    s["iddialar"] = [i for b in bolumler for i in b["iddialar"]]
    h = yapi_denetimi(s, len(gorseller), True, kaynak, kaynak_sayilari, koordinat)
    if h:
        print(f"    birleşik senaryo denetimi: {h[:4]}", flush=True)
        return None
    return s


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
        s = uzun_yaz(ortak, gorseller, kaynak, kaynak_sayilari, koordinat)
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
