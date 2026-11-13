"""İlk İngilizce dersleri e001-e004 (2026-11-13, elle). otonom/ingilizce_yaz.py bunları örnek alır.

Ders kalıbı (her kelime için): Türkçe durum -> İngilizce kelime (kartla) -> anlatıcı Türkçe anlamı söyler
ve "Sen de söyle!" der -> İngilizce kelime tekrar, sonra çocuğun tekrar etmesi için sessiz pay (bekle).
Hedef İngilizce kelime Türkçe satırda geçmez (Türkçe ses İngilizceyi bozar). Son çekim: hepsi bir arada.
Çalıştır: venv/bin/python seri/findik-ile-pamuk/ingilizce_yaz1.py
"""
import json
from pathlib import Path

KLASOR = Path(__file__).resolve().parent / "bolumler"


def T(kim, metin):
    return {"kim": kim, "metin": metin}


def E(kim, metin, anlam=None, bekle=None):
    s = {"kim": kim, "metin": metin, "dil": "en"}
    if anlam:
        s["anlam"] = anlam
    if bekle:
        s["bekle"] = bekle
    return s


def C(tip, hareket, hedef, satirlar, eylemler=(), isik="sabah"):
    return {"tip": tip, "hareket": hareket, "isik": isik, "hedef": hedef, "satirlar": satirlar,
            "eylemler": list(eylemler)}


def ey(kim, eylem, bas, **k):
    return {"kim": kim, "eylem": eylem, "bas": bas, **k}


def ders(no, konu, konu_en, kod, kelimeler, ekran, aciklama, mekan, baslangic, cekimler, nesneler=None,
         muzik="normal"):
    for i, c in enumerate(cekimler):
        c["id"] = f"c{i + 1}"
    kel_metin = ", ".join(k[0][:1].upper() + k[0][1:] for k in kelimeler)
    return {
        "seri_id": "findik-ile-pamuk", "bolum_no": no, "tur": "ingilizce",
        "baslik": f"{konu}: {kel_metin}", "deger": "İngilizce öğrenmek",
        "konu": konu, "konu_en": konu_en, "konu_kodu": kod,
        "kelimeler": [{"en": en, "tr": tr} for en, tr in kelimeler],
        "giris_metni": f"Fındık ile Pamuk İngilizce öğreniyor! Ders {no}: {konu}.",
        "onceki_olaylar": [], "bu_bolumde_degisen": [], "mekan": mekan, "baslangic": baslangic,
        "nesne_yerlesim": nesneler or {}, "ekran_basligi": ekran,
        "youtube": {"aciklama": aciklama}, "cekimler": cekimler, "muzik": muzik,
    }


DERSLER = [
    ders(1, "Selamlaşma", "Greetings", "selamlasma",
         [("hello", "merhaba"), ("thank you", "teşekkür ederim"), ("goodbye", "hoşça kal")],
         "Merhaba İngilizce Ne?", "Fındık ile Pamuk İngilizce selamlaşmayı öğretiyor: merhaba, teşekkür ederim, "
         "hoşça kal.", "orman", {"findik": [-0.6, 0.2], "pamuk": [0.5, 0.2]},
         [C("orta", "hizli_yaklas", ["findik"], [T("findik", "İngilizce selam vermeyi biliyor musun? Hadi öğrenelim!")],
            [ey("findik", "ifade", 0.0, tur="mutlu"), ey("findik", "el_salla", 0.3, son=0.8)]),
          C("iki_kisi", "yaklas", ["findik", "pamuk"],
            [E("findik", "Hello!", "merhaba"), E("pamuk", "Hello, friend!"),
             T("anlatici", "Merhaba demek. Hadi sen de söyle!"), E("findik", "Hello!", bekle=1.5)],
            [ey("findik", "el_salla", 0.0, son=0.25), ey("pamuk", "el_salla", 0.2, son=0.45),
             ey("pamuk", "ifade", 0.2, tur="mutlu"), ey("findik", "bak", 0.6, yon=0.0)]),
          C("orta", "takip", ["pamuk"],
            [T("pamuk", "Al, sana bir elma!"), E("findik", "Thank you!", "teşekkür ederim"),
             T("anlatici", "Teşekkür ederim demek. Sen de söyle!"), E("findik", "Thank you!", bekle=1.5)],
            [ey("pamuk", "tut", 0.0, nesne="elma", son=0.15), ey("pamuk", "ver", 0.2, nesne="elma", kime="findik", son=0.35),
             ey("findik", "ifade", 0.35, tur="mutlu")]),
          C("genis", "kaydir", ["findik", "pamuk"],
            [E("pamuk", "Goodbye!", "hoşça kal"), T("anlatici", "Hoşça kal demek. Hadi söyle!"),
             E("pamuk", "Goodbye!", bekle=1.5)],
            [ey("pamuk", "yuru", 0.0, nereye=[1.3, 0.3], son=0.4), ey("pamuk", "bak", 0.4, kime="findik"),
             ey("pamuk", "el_salla", 0.45, son=0.9)]),
          C("iki_kisi", "uzaklas", ["findik", "pamuk"],
            [E("findik", "Hello! Thank you! Goodbye!"), T("anlatici", "Bravo! Üç yeni İngilizce kelime öğrendin!")],
            [ey("findik", "zipla", 0.1, kez=1, son=0.4), ey("findik", "el_salla", 0.5, son=1.0),
             ey("pamuk", "el_salla", 0.52, son=1.0)])],
         nesneler={"elma": [0.8, 0.1, 0.0]}),

    ders(2, "Hareketler", "Action Words", "hareketler",
         [("jump", "zıpla"), ("run", "koş"), ("walk", "yürü")],
         "Zıpla İngilizce Ne?", "Fındık ile Pamuk ile İngilizce hareket kelimeleri: zıpla, koş, yürü. Çocuğunuz "
         "kelimeyi söylerken hareketi de yapsın!", "orman", {"findik": [-0.9, 0.2], "pamuk": [0.7, 0.2]},
         [C("orta", "hizli_yaklas", ["findik"], [T("findik", "Hazır mısın? İngilizce hareket oyunu başlıyor!")],
            [ey("findik", "ifade", 0.0, tur="kararli"), ey("findik", "zipla", 0.4, kez=1, son=0.8)]),
          C("orta", "sabit", ["findik"],
            [E("findik", "Jump!", "zıpla"), T("anlatici", "Zıpla demek. Sen de söyle ve zıpla!"),
             E("findik", "Jump, jump!", bekle=1.5)],
            [ey("findik", "zipla", 0.05, kez=1, son=0.25), ey("findik", "zipla", 0.6, kez=2, son=0.95)]),
          C("genis", "takip", ["pamuk"],
            [E("pamuk", "Run!", "koş"), T("anlatici", "Koş demek. Hadi söyle!"), E("pamuk", "Run, run!", bekle=1.5)],
            [ey("pamuk", "ifade", 0.0, tur="mutlu"), ey("pamuk", "kos", 0.05, nereye=[1.5, 0.3], son=0.4),
             ey("pamuk", "kos", 0.6, nereye=[0.2, 0.15], son=0.95)]),
          C("orta", "kaydir", ["findik"],
            [E("findik", "Walk!", "yürü"), T("anlatici", "Yürü demek. Sen de söyle!"),
             E("findik", "Walk, walk!", bekle=1.5)],
            [ey("findik", "yuru", 0.05, nereye=[-0.4, 0.25], son=0.45), ey("findik", "yuru", 0.6, nereye=[-0.1, 0.2], son=0.95)]),
          C("iki_kisi", "sars", ["findik", "pamuk"],
            [E("pamuk", "Jump! Run! Walk!"), T("anlatici", "Harika! Üç hareketi İngilizce söyledin!")],
            [ey("findik", "zipla", 0.05, kez=2, son=0.4), ey("pamuk", "zipla", 0.1, kez=2, son=0.45),
             ey("findik", "el_salla", 0.6, son=1.0), ey("pamuk", "el_salla", 0.62, son=1.0)])],
         muzik="macera"),

    ders(3, "Sayılar", "Numbers", "sayilar_1",
         [("one", "bir"), ("two", "iki"), ("three", "üç")],
         "Üçe Kadar Sayalım!", "Fındık zıplıyor, biz İngilizce sayıyoruz: bir, iki, üç. Çocuklar için İngilizce "
         "sayılar.", "orman", {"findik": [-0.4, 0.2], "pamuk": [0.8, 0.2]},
         [C("orta", "hizli_yaklas", ["pamuk"], [T("pamuk", "Fındık kaç kez zıplayacak? İngilizce sayalım!")],
            [ey("pamuk", "ifade", 0.0, tur="saskin"), ey("pamuk", "bak", 0.3, yon=0.0)]),
          C("orta", "sabit", ["findik"],
            [E("findik", "One!", "bir"), T("anlatici", "Bir demek. Sen de say!"), E("findik", "One!", bekle=1.2)],
            [ey("findik", "zipla", 0.05, kez=1, son=0.3), ey("findik", "zipla", 0.65, kez=1, son=0.95)]),
          C("orta", "yaklas", ["findik"],
            [E("findik", "Two!", "iki"), T("anlatici", "İki demek. Hadi say!"), E("findik", "One, two!", bekle=1.2)],
            [ey("findik", "zipla", 0.05, kez=2, son=0.35), ey("findik", "zipla", 0.6, kez=2, son=0.95)]),
          C("iki_kisi", "sabit", ["findik", "pamuk"],
            [E("pamuk", "Three!", "üç"), T("anlatici", "Üç demek. Sen de say!"), E("pamuk", "One, two, three!", bekle=1.5)],
            [ey("pamuk", "zipla", 0.05, kez=3, son=0.4), ey("findik", "zipla", 0.6, kez=3, son=0.98)]),
          C("iki_kisi", "uzaklas", ["findik", "pamuk"],
            [E("findik", "One, two, three!"), T("anlatici", "Süper! Üçe kadar İngilizce saydın!")],
            [ey("findik", "zipla", 0.05, kez=3, son=0.45), ey("pamuk", "zipla", 0.05, kez=3, son=0.45),
             ey("findik", "el_salla", 0.6, son=1.0), ey("pamuk", "el_salla", 0.62, son=1.0)])],
         muzik="macera"),

    ders(4, "İlk Kelimeler", "First Words", "ilk_kelimeler",
         [("apple", "elma"), ("ball", "top"), ("bucket", "kova")],
         "Elma İngilizce Ne?", "Fındık ile Pamuk ile ilk İngilizce kelimeler: elma, top, kova. Evdeki eşyaları "
         "İngilizce söyleme oyunu!", "orman", {"findik": [-0.8, 0.2], "pamuk": [0.8, 0.2]},
         [C("iki_kisi", "hizli_yaklas", ["findik", "pamuk"], [T("findik", "Bunların İngilizcesini biliyor musun?")],
            [ey("findik", "ifade", 0.0, tur="saskin"), ey("findik", "bak", 0.2, yon=0.0), ey("pamuk", "bak", 0.25, yon=0.0)]),
          C("orta", "yaklas", ["findik"],
            [E("findik", "Apple!", "elma"), T("anlatici", "Elma demek. Sen de söyle!"), E("findik", "Apple!", bekle=1.5)],
            [ey("findik", "tut", 0.0, nesne="elma", son=0.2), ey("findik", "ifade", 0.2, tur="mutlu")]),
          C("orta", "yaklas", ["pamuk"],
            [E("pamuk", "Ball!", "top"), T("anlatici", "Top demek. Hadi söyle!"), E("pamuk", "Ball!", bekle=1.5)],
            [ey("pamuk", "tut", 0.0, nesne="top", son=0.2), ey("pamuk", "zipla", 0.5, kez=1, son=0.8)]),
          C("iki_kisi", "sabit", ["findik", "pamuk"],
            [E("findik", "Bucket!", "kova"), T("anlatici", "Kova demek. Sen de söyle!"), E("findik", "Bucket!", bekle=1.5)],
            [ey("findik", "yuru", 0.0, nereye=[-0.3, 0.3], son=0.35), ey("findik", "bak", 0.4, yon=0.4),
             ey("findik", "zipla", 0.7, kez=1, son=0.95)]),
          C("iki_kisi", "uzaklas", ["findik", "pamuk"],
            [E("pamuk", "Apple! Ball! Bucket!"), T("anlatici", "Aferin! Üç yeni İngilizce kelime öğrendin!")],
            [ey("pamuk", "zipla", 0.1, kez=1, son=0.4), ey("findik", "el_salla", 0.55, son=1.0),
             ey("pamuk", "el_salla", 0.57, son=1.0)])],
         nesneler={"elma": [-0.5, 0.1, 0.0], "top": [0.5, 0.1, 0.0], "kova": [0.05, 0.35, 0.0]}),
]

if __name__ == "__main__":
    for d in DERSLER:
        yol = KLASOR / f"e{d['bolum_no']:03d}.json"
        yol.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        print("yazıldı", yol.name, d["baslik"])
