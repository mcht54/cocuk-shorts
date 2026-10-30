"""Wikipedia metni, sayfa görüntülenmeleri ve Wikimedia Commons görselleri (anahtarsız, ücretsiz API'ler).

Görsellerde yalnız yeniden kullanıma ve değiştirmeye izin veren lisanslar alınır: CC BY, CC BY-SA, CC0,
kamu malı. NC/ND, adil kullanım ve lisansı okunamayan her şey elenir.
"""
import html
import re
import time
from datetime import date, timedelta
from urllib.parse import quote

import requests

UA = {"User-Agent": "MerakArsiviBot/1.0 (https://github.com/mcht54/cocuk-shorts; YouTube documentary channel)"}
COMMONS = "https://commons.wikimedia.org/w/api.php"
IZINLI = re.compile(r"^(cc[ -]by(-sa)?[ -]?\d|cc0|public domain|pd\b|pd-)", re.I)
YASAK = re.compile(r"\b(nc|nd|non-?commercial|no ?deriv|fair use)\b", re.I)
GORSEL_DISI = re.compile(r"(logo|icon|flag of|coat of arms|map|harita|locator|diagram|svg|signature|"
                         r"seal of|emblem|stamp|banknote|coin|distribution|chart|graph|plan of|"
                         r"floor plan|scheme|infographic|screenshot|tablo|grafik)", re.I)


def _get(url, params, deneme=4):
    for i in range(deneme):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(10 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == deneme - 1:
                raise
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url} yanıt vermedi")


def temiz(metin):
    """HTML (kesilmiş olabilir) -> düz metin."""
    metin = re.sub(r"<[^>]*(>|$)", "", metin or "")
    return re.sub(r"\s+", " ", html.unescape(metin)).strip(" (")


def makale(baslik, dil="en"):
    """{'baslik','url','metin','uzunluk','diller':{dil:baslik}} ya da None (yoksa/yönlendirme belirsizse)."""
    v = _get(f"https://{dil}.wikipedia.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1, "titles": baslik,
        "prop": "extracts|langlinks|pageprops", "explaintext": 1, "lllimit": 500})
    sayfa = (v.get("query", {}).get("pages") or [{}])[0]
    if sayfa.get("missing") or "extract" not in sayfa or "disambiguation" in sayfa.get("pageprops", {}):
        return None
    metin = sayfa["extract"]
    # kaynakça / dış bağlantı bölümleri bilgi taşımaz
    metin = re.split(r"\n==+ ?(References|See also|External links|Notes|Further reading|Kaynakça|"
                     r"Ayrıca bakınız|Dış bağlantılar|Notlar|Kaynaklar) ?==+", metin)[0]
    t = sayfa["title"]
    return {"baslik": t, "url": f"https://{dil}.wikipedia.org/wiki/{quote(t.replace(' ', '_'))}",
            "metin": metin.strip(), "uzunluk": len(metin),
            "diller": {x["lang"]: x["title"] for x in sayfa.get("langlinks", [])}}


def goruntulenme(baslik, dil="en", gun=60):
    """Son `gun` günün toplam okunma sayısı (ilgi ölçüsü). Hata olursa 0."""
    bit = date.today() - timedelta(days=1)
    bas = bit - timedelta(days=gun)
    try:
        v = _get("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                 f"{dil}.wikipedia/all-access/user/{quote(baslik.replace(' ', '_'), safe='')}/daily/"
                 f"{bas:%Y%m%d}00/{bit:%Y%m%d}00", {})
        return sum(x["views"] for x in v.get("items", []))
    except Exception:
        return 0


def _imageinfo(sayfalar):
    out = []
    for s in sayfalar:
        ii = (s.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lisans = temiz(meta.get("LicenseShortName", {}).get("value", ""))
        if not IZINLI.search(lisans) or YASAK.search(lisans):
            continue
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        if ii.get("width", 0) < 1000 or ii.get("height", 0) < 560:
            continue
        if GORSEL_DISI.search(s["title"]):
            continue
        yazar = temiz(meta.get("Artist", {}).get("value", "")) or temiz(meta.get("Credit", {}).get("value", ""))
        if not yazar and not re.search(r"cc0|public domain|pd", lisans, re.I):
            continue  # CC BY/BY-SA yazar adı ister; adı bilinmeyen görsel kullanılmaz
        aciklama = temiz(meta.get("ImageDescription", {}).get("value", ""))
        if GORSEL_DISI.search(yazar) or re.match(r"(map|plan|diagram)\b", aciklama, re.I):
            continue
        out.append({
            "baslik": s["title"], "url": ii.get("thumburl") or ii["url"], "w": ii["width"], "h": ii["height"],
            "lisans": lisans, "yazar": (yazar or "Wikimedia Commons")[:80],
            "aciklama": temiz(meta.get("ImageDescription", {}).get("value", ""))[:160],
            "sayfa": "https://commons.wikimedia.org/wiki/" + quote(s["title"].replace(" ", "_")),
        })
    return out


def makale_gorselleri(baslik, dil="en"):
    """Wikipedia makalesinin kendi kullandığı görseller (en ilgili olanlar)."""
    v = _get(f"https://{dil}.wikipedia.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1, "titles": baslik,
        "generator": "images", "gimlimit": 100, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1920})
    return _imageinfo(v.get("query", {}).get("pages", []))


def commons_ara(sorgu, adet=40):
    v = _get(COMMONS, {
        "action": "query", "format": "json", "formatversion": 2, "generator": "search",
        "gsrsearch": f"{sorgu} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": adet,
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1920})
    sayfalar = sorted(v.get("query", {}).get("pages", []), key=lambda s: s.get("index", 0))
    return _imageinfo(sayfalar)


def gorseller(baslik, ek_sorgular=(), en_cok=60):
    """Önce makalenin görselleri, sonra Commons aramaları; tekrarsız, en çok `en_cok`."""
    tum, gorulen = [], set()
    kume = makale_gorselleri(baslik)
    for q in [baslik, *ek_sorgular]:
        kume += commons_ara(q)
    for g in kume:
        if g["baslik"] not in gorulen:
            gorulen.add(g["baslik"])
            tum.append(g)
    return tum[:en_cok]


def indir(g, hedef):
    """Görseli indir (önbellekli). Başarısızsa False."""
    if hedef.exists() and hedef.stat().st_size > 10_000:
        return True
    for i in range(4):
        try:
            r = requests.get(g["url"], headers=UA, timeout=120)
            if r.status_code == 429:
                time.sleep(15 * (i + 1))
                continue
            r.raise_for_status()
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(r.content)
            return True
        except requests.RequestException:
            time.sleep(5 * (i + 1))
    return False


def koordinat(baslik, dil="en"):
    """Wikidata P625 (enlem, boylam) ya da None — harita grafiği için."""
    try:
        v = _get(f"https://{dil}.wikipedia.org/w/api.php", {
            "action": "query", "format": "json", "formatversion": 2, "redirects": 1, "titles": baslik,
            "prop": "pageprops", "ppprop": "wikibase_item"})
        qid = (v.get("query", {}).get("pages") or [{}])[0].get("pageprops", {}).get("wikibase_item")
        if not qid:
            return None
        w = _get("https://www.wikidata.org/w/api.php", {"action": "wbgetclaims", "format": "json",
                                                          "entity": qid, "property": "P625"})
        d = w["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"]
        return [round(d["latitude"], 4), round(d["longitude"], 4)]
    except Exception:
        return None
