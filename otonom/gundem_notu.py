"""Güncel gündem notu (2026-11-27, Mücahit: "her hesap için yerel ve Türkiye geneli gündem bağlantısı").
gundem.json'daki maddeler web aramasıyla doğrulanmış, kaynaklı ve TARİHLİDİR: yazara yalnız bugün geçerli olanlar gider
(süresi geçen madde kendiliğinden düşer). Gündem her videoda zorunlu değil; varsayılan olarak haftada 3 gün (Pzt, Çar, Cum) eklenir.
Bağımlılık yok; aynı dosya bütün hatlara kopyalanır. Hata olursa boş döner, hat durmaz."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

KURAL = ("GÜNCEL GÜNDEM (doğrulanmış, kaynaklı; bugün geçerli olanlar). Kullanım kuralı: bu videoda gündem ZORUNLU DEĞİL. "
         "Yalnız markanın konusuna doğal bağlanan EN ÇOK BİR maddeyi seç; yoksa hiç kullanma. Rakam ve tarihleri BİREBİR kullan, "
         "yeni rakam UYDURMA; 'tahmini' ya da 'bildirildi' yazan maddeyi videoda da öyle söyle. Gündemi konunun kendisi yapma: "
         "izleyicinin parası/müşterisi/zamanıyla bağla, markanın işine çevir. Son konularda aynı gündem varsa tekrar etme.")


def metin(yol, gun: dt.date | None = None, gunler: tuple[int, ...] | None = (0, 2, 4), kural: str | None = None) -> str:
    try:
        gun = gun or dt.date.today()
        if gunler is not None and gun.weekday() not in gunler:
            return ""
        v = json.loads(pathlib.Path(yol).read_text(encoding="utf-8"))
        t = gun.isoformat()
        m = [x for x in v.get("maddeler", []) if x.get("bas", "0000") <= t <= x.get("bit", "0000")]
        if not m:
            return ""
        s = [kural or KURAL]
        for x in m[:8]:
            s.append(f"- {x['bilgi']} → Fikir: {x['fikir']} (geçerli: {x['bit']})")
        return "\n".join(s)
    except Exception:  # noqa: BLE001
        return ""
