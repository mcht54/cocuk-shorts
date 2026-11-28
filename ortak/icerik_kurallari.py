"""İçerik stratejisti kuralları (kullanıcı kuralı, 2026-11-28): yazı yazan Gemini istemlerine eklenir.

Tek kaynak ~/Documents/mcht-icerik-ortak/icerik-stratejisti.md; buradaki ortak/icerik-stratejisti.md onun birebir
kopyasıdır (kaynak değişince kopyala). Çocuk kanalının uyarlaması ayrı dosyada (icerik-stratejisti-cocuk.md);
ana metne dokunulmaz. Dosya yoksa/okunamazsa boş döner: hat durmaz.
"""
from __future__ import annotations

from pathlib import Path

KLASOR = Path(__file__).resolve().parent
ANA = KLASOR / "icerik-stratejisti.md"
COCUK = KLASOR / "icerik-stratejisti-cocuk.md"

KANCA_NOTU = ('KANCA ADAYLARI (kural 2): JSON\'a isteğe bağlı "kanca_adaylari" listesi ekle: farklı tipte en az 5 açılış '
              '(ekran yazısı + ilk cümle). En güçlüsünü seç ve onu asıl alanlarda (ekran yazısı/başlık ve ilk cümle) kullan; aday listesi yayınlanmaz.')


def _oku(yol: Path) -> str:
    try:
        return yol.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def metin(cocuk: bool = False, son_acilislar=None, kanca_alani: bool = True) -> str:
    """İsteme eklenecek blok; kural dosyası yoksa ''. son_acilislar: son kullanılan açılışlar (kural 7)."""
    ana = _oku(ANA)
    if not ana:
        return ""
    s = [ana]
    if cocuk:
        ek = _oku(COCUK)
        if ek:
            s.append(ek)
    if kanca_alani:
        s.append(KANCA_NOTU)
    acilis = [str(a).strip() for a in (son_acilislar or []) if str(a or "").strip()]
    if acilis:
        s.append("SON KULLANILAN AÇILIŞLAR (kural 7: bunları ve aynı kanca tipini art arda TEKRARLAMA):\n"
                 + "\n".join(f"- {a[:140]}" for a in acilis[-12:]))
    return "\n\n".join(s)


def bolum_acilislari(bolumler, n=10) -> list[str]:
    """Fındık ile Pamuk bölümlerinin açılışları (ekran yazısı | ilk satır), en yenisi sonda (kural 7)."""
    out = []
    for b in list(bolumler or [])[-n:]:
        try:
            ilk = next((s.get("metin", "") for c in b.get("cekimler", []) for s in c.get("satirlar", [])), "")
            a = f"{b.get('ekran_basligi', '')} | {ilk}".strip(" |")
        except (AttributeError, TypeError):
            continue
        if a:
            out.append(a)
    return out


DEPO = KLASOR.parent
OLCUM_EN_AZ = 6      # bundan az ölçülmüş bölüm varsa blok eklenmez
OLCUM_OLGUNLUK = 3   # ölçümden en az bu kadar gün önce yayınlanmış video sayılır (yeni video izlenmesi oturmamış)


def olcum_blogu(onek: str, depo: Path | None = None, adet: int = 3) -> str:
    """Kural 8: otonom/izlenme.json + yayin_kaydi.json'dan en çok/en az izlenen bölümler (onek: "b" masal,
    "e" İngilizce). Yalnız ölçülen izlenme yazılır; veri az ya da dosya yok/bozuksa ''."""
    import datetime as dt
    import json
    depo = depo or DEPO
    try:
        rapor = json.loads((depo / "otonom" / "izlenme.json").read_text(encoding="utf-8"))
        kayit = json.loads((depo / "yayin_kaydi.json").read_text(encoding="utf-8"))
        olcum_gunu = dt.date.fromisoformat(str(rapor.get("tarih", ""))[:10])
        bolum_yolu = {k.get("video_id"): k.get("bolum", "") for k in kayit if isinstance(k, dict)}
        satirlar = []
        for v in rapor.get("videolar", []):
            yol = bolum_yolu.get(v.get("video_id"), "")
            if v.get("profil") != "shorts" or v.get("durum") != "public" or not Path(yol).name.startswith(onek) or not isinstance(v.get("izlenme"), int):
                continue
            try:
                if (olcum_gunu - dt.date.fromisoformat(str(v.get("yayin", ""))[:10])).days < OLCUM_OLGUNLUK:
                    continue
                b = json.loads((depo / yol).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            acilis = (bolum_acilislari([b]) or [""])[0]
            satirlar.append((v["izlenme"], f"«{b.get('baslik') or v.get('ad', '')}» açılış: {acilis or '-'} "
                                           f"— {v['izlenme']} izlenme ({v.get('yayin', '')} yayın)"))
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    return _olcum_metni(satirlar, olcum_gunu, adet, "bölüm")


def _olcum_metni(satirlar, olcum_gunu, adet, birim) -> str:
    if len(satirlar) < OLCUM_EN_AZ:
        return ""
    satirlar = sorted(satirlar, key=lambda x: -x[0])
    n = min(adet, len(satirlar) // 2)
    return ("NE TUTUYOR / NE TUTMUYOR (ölçüm, " + olcum_gunu.isoformat() + "; YouTube izlenmesi, " + str(len(satirlar))
            + f" {birim}). Tutanların kanca tipini, konusunu ve ilk cümle yapısını taşı; tutmayanların açılışını tekrarlama. "
              "Bu rakamları videoda kullanma.\nEN ÇOK İZLENEN:\n" + "\n".join("- " + s for _, s in satirlar[:n])
            + "\nEN AZ İZLENEN:\n" + "\n".join("- " + s for _, s in satirlar[-n:]))


def merak_olcum_blogu(profil: str, merak: Path | None = None, adet: int = 3) -> str:
    """Kural 8, Merak Arşivi: merak/izlenme.json (merak.izlenme toplar) + konular/<konu>/<senaryo>.json.
    profil "shorts" ya da "uzun". Aynı eşikler (≥6 ölçülmüş, 3 günden yeni hariç); yoksa/bozuksa ''."""
    import datetime as dt
    import json
    merak = merak or DEPO / "merak"
    try:
        rapor = json.loads((merak / "izlenme.json").read_text(encoding="utf-8"))
        olcum_gunu = dt.date.fromisoformat(str(rapor.get("tarih", ""))[:10])
        satirlar = []
        for v in rapor.get("videolar", []):
            if v.get("profil") != profil or v.get("durum") != "public" or not isinstance(v.get("izlenme"), int):
                continue
            try:
                if (olcum_gunu - dt.date.fromisoformat(str(v.get("yayin", ""))[:10])).days < OLCUM_OLGUNLUK:
                    continue
                s = json.loads((merak / "konular" / str(v["konu"]) / f"{v['senaryo']}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            parcalar = s.get("parcalar") or ((s.get("bolumler") or [{}])[0].get("parcalar") or [])
            ilk = parcalar[0].get("metin", "") if parcalar and isinstance(parcalar[0], dict) else ""
            ekran = s.get("ekran_basligi") or s.get("kapak_yazisi") or ""
            satirlar.append((v["izlenme"], f"«{s.get('baslik', '')}» açılış: {ekran} | {ilk} "
                                           f"— {v['izlenme']} izlenme ({v.get('yayin', '')} yayın)"))
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    return _olcum_metni(satirlar, olcum_gunu, adet, "video")


def ekle(istem: str, **kw) -> str:
    """istem + kurallar bloğu (kurallar yoksa istem aynen)."""
    m = metin(**kw)
    return f"{istem}\n\n{m}" if m else istem
