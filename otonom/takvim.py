"""Yayın takvimi: her hat için haftalık yayın saatleri (slotlar) ve hangilerinin dolu olduğu.

Videolar ONAY_UFKU kadar önceden üretilip YouTube'a zamanlanmış (private + publishAt) yüklenir; kullanıcı
haftalık e-postadaki listeden beğenmediğini Studio'da siler/gizler, dokunmadığı saatinde yayınlanır.
Saati geçmek üzere olan boş slot (ör. sistem yeni açıldı ya da birkaç gün çalışmadı) hemen yayınlanır,
böylece takvimde boşluk kalmaz.
"""
from datetime import datetime, timedelta, timezone

# hat: (haftanın günleri 0=pazartesi, saat UTC). Türkiye = UTC+3.
SLOTLAR = {
    "masal_shorts": (range(7), 14),             # her gün 17:00
    "merak_uzun": ((1, 4), 15),                 # salı, cuma 18:00
    "merak_shorts": ((0, 2, 3, 5), 16),         # pzt, çar, per, cmt 19:00
}
ONAY_UFKU = timedelta(days=7)
GECIKME_PAYI = timedelta(hours=12)   # saati bu kadar önce geçmiş boş slot hâlâ (hemen) doldurulur
HEMEN = timedelta(minutes=20)        # yayın saatine bundan az kaldıysa zamanlama yerine hemen yayınla


def slotlar(hat, bas, bit):
    gunler, saat = SLOTLAR[hat]
    gun = bas.replace(hour=saat, minute=0, second=0, microsecond=0) - timedelta(days=1)
    out = []
    while gun <= bit:
        if gun.weekday() in gunler and bas <= gun <= bit:
            out.append(gun)
        gun += timedelta(days=1)
    return out


def dolu(kayitlar):
    """Kayıtlarda yüklenmiş videoların yayın zamanları (zamanlanmış ya da hemen yayınlanmış)."""
    out = set()
    for k in kayitlar:
        if k.get("durum") == "yuklendi" and k.get("yayin_zamani"):
            out.add(datetime.fromisoformat(k["yayin_zamani"]))
    return out


def bos_slotlar(hat, kayitlar, simdi=None):
    """Doldurulması gereken slotlar, en yakından uzağa."""
    simdi = simdi or datetime.now(timezone.utc)
    alinan = dolu(kayitlar)
    return [s for s in slotlar(hat, simdi - GECIKME_PAYI, simdi + ONAY_UFKU)
            if not any(abs((s - d).total_seconds()) < 3 * 3600 for d in alinan)]


def yukleme_zamani(slot, simdi=None):
    """(publishAt ya da None=hemen, kayda yazılacak yayın zamanı)."""
    simdi = simdi or datetime.now(timezone.utc)
    if slot - simdi < HEMEN:
        return None, simdi
    return slot, slot
