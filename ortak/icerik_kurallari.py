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


def ekle(istem: str, **kw) -> str:
    """istem + kurallar bloğu (kurallar yoksa istem aynen)."""
    m = metin(**kw)
    return f"{istem}\n\n{m}" if m else istem
