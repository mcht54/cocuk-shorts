"""Yapay zekâ görseli alınamadığında yerel sahne çizimi.

Ortam (orman, deniz, gece...) PIL ile çizilir; hayvan/nesne figürleri Google Noto
Emoji görselleridir (Apache 2.0, assets/emoji). Aynı videoda ana karakter her
sahnede aynı figürdür. Ağ gerektirmez, her zaman sahneye özgü bir görsel döner.
"""
import math
import random
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

G, Y = 1080, 1920
EMOJI = Path(__file__).resolve().parent.parent / "assets" / "emoji"

# anahtar: (Noto kod noktası, İngilizce anahtar kelimeler, tür)
KATALOG = {
    # hayvanlar
    "sincap": ("1f43f", "squirrel chipmunk", "hayvan"),
    "tavsan": ("1f430", "rabbit bunny hare", "hayvan"),
    "kedi": ("1f431", "cat kitten kitty", "hayvan"),
    "kopek": ("1f436", "dog puppy doggy", "hayvan"),
    "ayi": ("1f43b", "bear", "hayvan"),
    "panda": ("1f43c", "panda", "hayvan"),
    "tilki": ("1f98a", "fox", "hayvan"),
    "aslan": ("1f981", "lion", "hayvan"),
    "kaplan": ("1f42f", "tiger", "hayvan"),
    "maymun": ("1f435", "monkey", "hayvan"),
    "fil": ("1f418", "elephant", "hayvan"),
    "zurafa": ("1f992", "giraffe", "hayvan"),
    "zebra": ("1f993", "zebra", "hayvan"),
    "at": ("1f434", "horse pony", "hayvan"),
    "inek": ("1f42e", "cow calf", "hayvan"),
    "domuz": ("1f437", "pig piglet", "hayvan"),
    "koyun": ("1f411", "sheep lamb", "hayvan"),
    "tavuk": ("1f414", "chicken hen", "hayvan"),
    "civciv": ("1f425", "chick", "hayvan"),
    "ordek": ("1f986", "duck duckling", "hayvan"),
    "baykus": ("1f989", "owl", "hayvan"),
    "penguen": ("1f427", "penguin", "hayvan"),
    "kurbaga": ("1f438", "frog toad", "hayvan"),
    "kaplumbaga": ("1f422", "turtle tortoise", "hayvan"),
    "salyangoz": ("1f40c", "snail", "hayvan"),
    "kelebek": ("1f98b", "butterfly", "hayvan"),
    "ari": ("1f41d", "bee honeybee", "hayvan"),
    "ugurbocegi": ("1f41e", "ladybug ladybird", "hayvan"),
    "ahtapot": ("1f419", "octopus", "hayvan"),
    "balik": ("1f41f", "fish", "hayvan"),
    "tropikal_balik": ("1f420", "tropical fish clownfish", "hayvan"),
    "balina": ("1f433", "whale", "hayvan"),
    "yunus": ("1f42c", "dolphin", "hayvan"),
    "yengec": ("1f980", "crab", "hayvan"),
    "denizanasi": ("1fabc", "jellyfish", "hayvan"),
    "kirpi": ("1f994", "hedgehog", "hayvan"),
    "fare": ("1f42d", "mouse", "hayvan"),
    "koala": ("1f428", "koala", "hayvan"),
    "hamster": ("1f439", "hamster", "hayvan"),
    "unicorn": ("1f984", "unicorn", "hayvan"),
    "dinozor": ("1f995", "dinosaur sauropod brontosaurus", "hayvan"),
    "kus": ("1f426", "bird sparrow", "hayvan"),
    "papagan": ("1f99c", "parrot", "hayvan"),
    "kugu": ("1f9a2", "swan", "hayvan"),
    "flamingo": ("1f9a9", "flamingo", "hayvan"),
    "kunduz": ("1f9ab", "beaver", "hayvan"),
    "tembel_hayvan": ("1f9a5", "sloth", "hayvan"),
    "kanguru": ("1f998", "kangaroo", "hayvan"),
    "deve": ("1f42a", "camel", "hayvan"),
    "fok": ("1f9ad", "seal", "hayvan"),
    # yiyecek
    "palamut": ("1f330", "acorn chestnut nut hazelnut", "nesne"),
    "elma": ("1f34e", "apple", "nesne"),
    "muz": ("1f34c", "banana", "nesne"),
    "cilek": ("1f353", "strawberry", "nesne"),
    "havuc": ("1f955", "carrot", "nesne"),
    "portakal": ("1f34a", "tangerine", "nesne"),
    "uzum": ("1f347", "grape grapes", "nesne"),
    "karpuz": ("1f349", "watermelon", "nesne"),
    "kiraz": ("1f352", "cherry cherries", "nesne"),
    "armut": ("1f350", "pear", "nesne"),
    "limon": ("1f34b", "lemon", "nesne"),
    "bal": ("1f36f", "honey", "nesne"),
    "pasta": ("1f382", "cake", "nesne"),
    "kurabiye": ("1f36a", "cookie biscuit", "nesne"),
    "sut": ("1f95b", "milk", "nesne"),
    "ekmek": ("1f35e", "bread", "nesne"),
    "peynir": ("1f9c0", "cheese", "nesne"),
    "misir": ("1f33d", "corn", "nesne"),
    "domates": ("1f345", "tomato", "nesne"),
    # doğa
    "gunes": ("1f31e", "sun sunshine", "doga"),
    "ay": ("1f319", "moon crescent", "doga"),
    "yildiz": ("2b50", "star stars", "doga"),
    "bulut": ("2601", "cloud clouds", "doga"),
    "gokkusagi": ("1f308", "rainbow", "doga"),
    "cicek": ("1f33c", "flower flowers blossom daisy", "doga"),
    "aycicegi": ("1f33b", "sunflower", "doga"),
    "lale": ("1f337", "tulip", "doga"),
    "gul": ("1f339", "rose", "doga"),
    "agac": ("1f333", "tree", "doga"),
    "cam_agaci": ("1f332", "pine evergreen fir", "doga"),
    "yaprak": ("1f343", "leaf leaves", "doga"),
    "sonbahar_yapragi": ("1f341", "maple autumn", "doga"),
    "mantar": ("1f344", "mushroom", "doga"),
    "filiz": ("1f331", "seedling sprout seed plant", "doga"),
    "kar_tanesi": ("2744", "snowflake snow", "doga"),
    "kardan_adam": ("26c4", "snowman", "doga"),
    "damla": ("1f4a7", "drop raindrop water tear", "doga"),
    "deniz_kabugu": ("1f41a", "shell seashell", "doga"),
    "mercan": ("1fab8", "coral reef", "doga"),
    "kaya": ("1faa8", "rock stone pebble", "doga"),
    "kaktus": ("1f335", "cactus", "doga"),
    "semsiye": ("2602", "umbrella rain", "doga"),
    "gezegen": ("1fa90", "planet saturn", "doga"),
    "kutuk": ("1fab5", "log wood", "doga"),
    # eşyalar
    "top": ("26bd", "ball football soccer", "nesne"),
    "balon": ("1f388", "balloon balloons", "nesne"),
    "hediye": ("1f381", "gift present", "nesne"),
    "oyuncak_ayi": ("1f9f8", "teddy toy toys", "nesne"),
    "kitap": ("1f4d6", "book reading", "nesne"),
    "boya": ("1f58d", "crayon crayons", "nesne"),
    "palet": ("1f3a8", "paint palette painting", "nesne"),
    "ucurtma": ("1fa81", "kite", "nesne"),
    "araba": ("1f697", "car", "nesne"),
    "otobus": ("1f68c", "bus", "nesne"),
    "tren": ("1f682", "train locomotive", "nesne"),
    "ucak": ("2708", "airplane plane aeroplane", "nesne"),
    "roket": ("1f680", "rocket spaceship", "nesne"),
    "tekne": ("26f5", "boat sailboat ship", "nesne"),
    "bisiklet": ("1f6b2", "bicycle bike", "nesne"),
    "ev": ("1f3e0", "house home cottage", "nesne"),
    "yatak": ("1f6cf", "bed", "nesne"),
    "dis_fircasi": ("1faa5", "toothbrush teeth", "nesne"),
    "sabun": ("1f9fc", "soap wash", "nesne"),
    "kavanoz": ("1fad9", "jar", "nesne"),
    "okul": ("1f3eb", "school", "nesne"),
    "canta": ("1f392", "backpack bag", "nesne"),
    "kalp": ("2764", "heart hearts love", "efekt"),
    "parilti": ("2728", "sparkle sparkles magic glitter", "efekt"),
    "nota": ("1f3b5", "music song singing", "efekt"),
    "uyku": ("1f4a4", "sleep sleeping asleep", "efekt"),
    "kirmizi": ("1f534", "red", "renk"),
    "sari": ("1f7e1", "yellow", "renk"),
    "yesil": ("1f7e2", "green", "renk"),
    "mavi": ("1f535", "blue", "renk"),
    "turuncu": ("1f7e0", "tangerinecolor", "renk"),
    "mor": ("1f7e3", "purple violet", "renk"),
    "kare": ("1f7e5", "square", "sekil"),
    "ucgen": ("1f53a", "triangle", "sekil"),
    "daire": ("26aa", "circle", "sekil"),
    **{f"sayi_{n}": (f"{0x30 + n:04x}_20e3", f"number{n}", "sayi") for n in range(10)},
    "sayi_10": ("1f51f", "number10 ten", "sayi"),
}

ORTAMLAR = {
    "orman": "forest woods woodland jungle",
    "deniz": "underwater sea ocean reef aquarium deep",
    "gol": "pond lake river",
    "cayir": "meadow field grass garden park hill",
    "ciftlik": "farm barn",
    "gece": "night bedtime moonlight starry",
    "oda": "room bedroom kitchen indoors house inside classroom",
    "kar": "snow winter snowy ice arctic",
    "uzay": "space galaxy cosmos",
    "gokyuzu": "sky clouds flying",
    "sade": "white background|plain background|simple background",
}

DUYGU = {"sad": "damla", "crying": "damla", "happy": "parilti", "laugh": "parilti",
         "smil": "parilti", "love": "kalp", "hug": "kalp", "friend": "kalp",
         "sleep": "uyku", "sing": "nota", "magic": "parilti", "wave": "parilti"}


def _kelime_bul(metin, kelimeler):
    metin = metin.lower()
    konumlar = []
    for k in (kelimeler.split("|") if "|" in kelimeler else kelimeler.split()):
        m = re.search(r"\b" + re.escape(k) + r"(e?s)?\b", metin)
        if m:
            konumlar.append(m.start())
    return min(konumlar) if konumlar else None


def ogeleri_bul(metin):
    """İngilizce görsel tarifinden katalog öğelerini geçtiği sırayla çıkar."""
    bulunan = []
    for ad, (_, kelimeler, tur) in KATALOG.items():
        if tur in ("renk", "sekil", "sayi"):  # bunlar yalnız senaryo "ogeler" ile açıkça istenir
            continue
        k = _kelime_bul(metin, kelimeler)
        if k is not None:
            bulunan.append((k, ad))
    # "sunflower" bulunduysa "sun"/"flower" gibi alt eşleşmeleri ele
    adlar = [a for _, a in sorted(bulunan)]
    if "aycicegi" in adlar:
        adlar = [a for a in adlar if a not in ("gunes", "cicek")]
    return adlar


def ortam_bul(metin, varsayilan="cayir"):
    en_iyi, konum = None, None
    for ad, kelimeler in ORTAMLAR.items():
        k = _kelime_bul(metin, kelimeler)
        if k is not None and (konum is None or k < konum):
            en_iyi, konum = ad, k
    return en_iyi or varsayilan


def ana_karakter(senaryo):
    """Karakter tarifinden (yoksa ilk sahneden) videonun ana figürünü seç."""
    for kaynak in (senaryo.get("karakter_tarifi", ""), senaryo["sahneler"][0].get("gorsel", "")):
        for ad in ogeleri_bul(kaynak):
            if KATALOG[ad][2] == "hayvan":
                return ad
    return None


@lru_cache(maxsize=256)
def _emoji(ad, boyut):
    kod = KATALOG[ad][0]
    img = Image.open(EMOJI / f"emoji_u{kod}.png").convert("RGBA")
    return img.resize((boyut, boyut), Image.LANCZOS)


def _cikartma(ad, boyut):
    """Beyaz çerçeveli, çizim kitabı tarzı figür."""
    img = _emoji(ad, boyut)
    pay = max(8, boyut // 22)
    tuval = Image.new("RGBA", (boyut + 2 * pay, boyut + 2 * pay))
    tuval.paste(img, (pay, pay), img)
    alfa = tuval.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    cerceve = alfa.filter(ImageFilter.MaxFilter(pay * 2 - 1 if pay % 2 else pay * 2 + 1))
    sonuc = Image.new("RGBA", tuval.size, (255, 255, 255, 0))
    sonuc.putalpha(cerceve)
    beyaz = Image.new("RGBA", tuval.size, (255, 255, 255, 255))
    sonuc = Image.composite(beyaz, sonuc, cerceve)
    sonuc.alpha_composite(tuval)
    return sonuc


def _degrade(ust, alt, h=Y, w=G):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for yy in range(h):
        t = yy / h
        d.line([(0, yy), (w, yy)], fill=tuple(int(ust[i] * (1 - t) + alt[i] * t) for i in range(3)))
    return img


def _tepe(d, ufuk, renk, r, genlik=60):
    noktalar = [(0, Y)]
    faz = r.random() * 6
    for x in range(0, G + 40, 40):
        noktalar.append((x, ufuk + genlik * math.sin(x / 210 + faz)))
    noktalar.append((G, Y))
    d.polygon(noktalar, fill=renk)


def _koy(img, ad, x, y, boyut, golge=True):
    s = _cikartma(ad, boyut)
    if golge:
        g = Image.new("RGBA", img.size)
        ImageDraw.Draw(g).ellipse([x - boyut * 0.38, y + boyut * 0.42, x + boyut * 0.38,
                                   y + boyut * 0.54], fill=(0, 0, 0, 55))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(14)))
    img.alpha_composite(s, (int(x - s.width / 2), int(y - s.height / 2)))


def arka_plan(ortam, r, gok_cismi=True):
    ufuk = 1180
    if ortam == "deniz":
        img = _degrade((120, 220, 235), (30, 90, 170)).convert("RGBA")
        katman = Image.new("RGBA", img.size)
        dk = ImageDraw.Draw(katman)
        for i in range(5):  # ışık huzmeleri
            x = r.randint(0, G)
            dk.polygon([(x - 40, 0), (x + 40, 0), (x + 220, Y), (x - 120, Y)], fill=(255, 255, 255, 28))
        img.alpha_composite(katman.filter(ImageFilter.GaussianBlur(20)))
        d = ImageDraw.Draw(img)
        for _ in range(26):
            x, yy, rr = r.randint(0, G), r.randint(0, Y), r.randint(6, 26)
            d.ellipse([x - rr, yy - rr, x + rr, yy + rr], outline=(225, 245, 255), width=4)
        d.ellipse([-200, 1500, G + 200, 2300], fill=(240, 215, 160, 255))
        for x in (90, 990):
            _koy(img, "mercan", x, 1560, 260, golge=False)
        _koy(img, "deniz_kabugu", 300, 1700, 130, golge=False)
        _koy(img, "tropikal_balik", r.choice([150, 930]), 640, 150, golge=False)  # başlık alanının altında
        return img
    if ortam == "uzay":
        img = _degrade((40, 20, 90), (90, 50, 160)).convert("RGBA")
        d = ImageDraw.Draw(img)
        for _ in range(120):
            x, yy, rr = r.randint(0, G), r.randint(0, Y), r.choice([2, 3, 4])
            d.ellipse([x - rr, yy - rr, x + rr, yy + rr], fill=(255, 255, 230))
        _koy(img, "gezegen", 860, 330, 260, golge=False)
        _koy(img, "yildiz", 180, 520, 110, golge=False)
        return img
    if ortam == "oda":
        img = _degrade((255, 236, 214), (255, 220, 200)).convert("RGBA")
        d = ImageDraw.Draw(img)
        for yy in range(60, ufuk, 120):
            for x in range(60 + (yy // 120 % 2) * 60, G, 120):
                d.ellipse([x - 9, yy - 9, x + 9, yy + 9], fill=(255, 205, 190))
        d.rounded_rectangle([640, 230, 980, 600], 30, fill=(170, 220, 250), outline=(255, 255, 255), width=22)
        _koy(img, "bulut", 810, 400, 150, golge=False)
        d.rectangle([0, ufuk, G, Y], fill=(214, 160, 110))
        for yy in range(ufuk + 70, Y, 90):
            d.line([(0, yy), (G, yy)], fill=(196, 140, 92), width=6)
        return img
    if ortam == "sade":
        img = _degrade((255, 250, 235), (255, 236, 245)).convert("RGBA")
        d = ImageDraw.Draw(img)
        for _ in range(40):
            x, yy, rr = r.randint(0, G), r.randint(0, Y), r.randint(8, 22)
            d.ellipse([x - rr, yy - rr, x + rr, yy + rr],
                      fill=r.choice([(255, 200, 200), (200, 230, 255), (255, 240, 180), (210, 245, 210)]))
        return img

    gece = ortam == "gece"
    kar = ortam == "kar"
    gok = {True: ((25, 35, 90), (90, 80, 160))}.get(gece, ((150, 215, 255), (225, 245, 255)))
    img = _degrade(*gok).convert("RGBA")
    d = ImageDraw.Draw(img)
    if gece:
        for _ in range(60):
            x, yy, rr = r.randint(0, G), r.randint(0, ufuk), r.choice([2, 3, 4])
            d.ellipse([x - rr, yy - rr, x + rr, yy + rr], fill=(255, 250, 210))
        if gok_cismi:
            _koy(img, "ay", 850, 300, 220, golge=False)
    else:
        if gok_cismi:
            _koy(img, "gunes", 880, 280, 230, golge=False)
        for x, yy, b in ((180, 260, 210), (520, 420, 150)):
            _koy(img, "bulut", x, yy, b, golge=False)
    if ortam == "gokyuzu":
        _koy(img, "gokkusagi", 300, 700, 380, golge=False)
        _koy(img, "bulut", 760, 1500, 330, golge=False)
        _koy(img, "bulut", 260, 1650, 280, golge=False)
        return img
    uzak = (60, 70, 130) if gece else (240, 248, 255) if kar else (150, 210, 130)
    yakin = (40, 60, 100) if gece else (255, 255, 255) if kar else (110, 190, 90)
    _tepe(d, ufuk - 90, uzak, r)
    if ortam == "orman":
        for x in range(-40, G + 80, 150):
            _koy(img, r.choice(["agac", "cam_agaci"]), x + r.randint(-30, 30),
                 ufuk - 160 + r.randint(-30, 30), r.randint(260, 340), golge=False)
    if kar:
        for x in (120, 960):
            _koy(img, "cam_agaci", x, ufuk - 120, 300, golge=False)
    _tepe(d, ufuk, yakin, r, genlik=35)
    if ortam == "gol":
        d.ellipse([60, 1480, G - 60, 1760], fill=(110, 190, 235))
        d.ellipse([140, 1520, G - 140, 1700], fill=(140, 210, 245))
    if ortam == "ciftlik":
        _koy(img, "ev", 150, ufuk - 80, 240, golge=False)
    if not (gece or kar):
        for x in (110, 330, 760, 980):
            _koy(img, r.choice(["cicek", "lale", "aycicegi"]), x, r.randint(1640, 1800), 120, golge=False)
    if kar:
        for _ in range(30):
            x, yy, rr = r.randint(0, G), r.randint(0, Y), r.randint(5, 12)
            d.ellipse([x - rr, yy - rr, x + rr, yy + rr], fill=(255, 255, 255))
    return img


def sahne_ciz(sahne, karakter, tohum, onceki_ortam="cayir"):
    """Sahne tarifinden çizim üret. sahne: {"gorsel", isteğe bağlı "ortam", "ogeler"}."""
    r = random.Random(tohum)
    tarif = sahne.get("gorsel", "")
    ortam = sahne.get("ortam") if sahne.get("ortam") in ORTAMLAR else ortam_bul(tarif, onceki_ortam)
    ogeler = [o for o in (sahne.get("ogeler") or ogeleri_bul(tarif)) if o in KATALOG]
    # güneş/ay sahnenin konusuysa (ilk öğe) figür olarak büyük çizilir, arka plandaki gizlenir;
    # değilse arka planda zaten olduğundan tekrar konmaz
    konu_gok = bool(ogeler) and ogeler[0] in ("gunes", "ay")
    ogeler = [o for o in ogeler if o not in ("agac", "cam_agaci", "bulut", "mercan")
              and (konu_gok or o not in ("gunes", "ay"))]
    duygular = [v for k, v in DUYGU.items() if k in tarif.lower()]
    img = arka_plan(ortam, r, gok_cismi=not konu_gok)

    figurler = []
    if karakter:
        figurler.append(karakter)
    figurler += [o for o in ogeler if o != karakter and KATALOG[o][2] != "efekt"]
    figurler = list(dict.fromkeys(figurler))[:4]
    if not figurler:  # tarifte tanınan hiçbir şey yoksa ortama uygun bir figür
        figurler = [{"deniz": "tropikal_balik", "gece": "baykus", "uzay": "roket",
                     "kar": "penguen", "oda": "oyuncak_ayi"}.get(ortam, "kelebek")]

    ana, yanlar = figurler[0], figurler[1:]
    _koy(img, ana, 540 if not yanlar else 470, 900, 600 if len(yanlar) < 2 else 520)
    yerler = [(820, 1000, 330), (230, 620, 250), (850, 600, 240)]
    for ad, (x, y, b) in zip(yanlar, yerler):
        _koy(img, ad, x, y, b)
    efektler = list(dict.fromkeys(duygular + [o for o in ogeler if KATALOG[o][2] == "efekt"]))[:2]
    for ad, (x, y) in zip(efektler, [(760, 560), (300, 520)]):
        _koy(img, ad, x + r.randint(-40, 40), y + r.randint(-40, 40), 150, golge=False)
    return img.convert("RGB"), ortam


def gerekli_kodlar():
    return sorted({k for k, _, _ in KATALOG.values()})
