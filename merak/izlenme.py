"""Merak Arşivi izlenme toplayıcı (yalnız okuma; 2026-11-28, kural 8 "performansı takip et, başarısızdan öğren").

Video ↔ senaryo eşlemesi: yüklemede merak/kayit.json'a yazılan konu+senaryo+video_id. Kayıtta olmayan eski
kanal videoları başlıkla (konular/*/uzun.json, kisa*.json "baslik") eşlenir. Rapor merak/izlenme.json'a yazılır;
yazar istemleri (merak/yaz.py) buradan "ne tutuyor / ne tutmuyor" bloğu alır (ortak/icerik_kurallari).
Kimlik: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN (Merak kanalının, MERAK_YT_REFRESH_TOKEN). Anahtar yoksa
ya da API hata verirse rapora dokunmadan 0 ile çıkar: büyüme işi durmaz.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
KONULAR = KOK / "konular"
KAYIT = KOK / "kayit.json"
RAPOR = KOK / "izlenme.json"
API = "https://www.googleapis.com/youtube/v3"


def ozet(metin):
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a") as f:
            f.write(metin + "\n")
    print(metin, flush=True)


def baslik_norm(b):
    b = re.sub(r"#\w+", " ", str(b or "").lower())
    return re.sub(r"\W+", " ", b).strip()


def senaryo_basliklari():
    """{normalize başlık: (konu, senaryo, profil)} — eski videoları eşlemek için."""
    out = {}
    for yol in sorted(KONULAR.glob("*/*.json")):
        if yol.stem != "uzun" and not yol.stem.startswith("kisa"):
            continue
        try:
            b = json.loads(yol.read_text()).get("baslik")
        except (OSError, ValueError, AttributeError):
            continue
        if b:
            out[baslik_norm(b)] = (yol.parent.name, yol.stem, "uzun" if yol.stem == "uzun" else "shorts")
    return out


def eslestir(kayitlar, kanal_videolari, basliklar):
    """Kayıttaki yüklemeler + başlıkla eşlenen kanal videoları: [{video_id, konu, senaryo, profil, yayin}]."""
    out, gorulen = [], set()
    for k in kayitlar:
        if k.get("durum") == "yuklendi" and k.get("video_id") and k["video_id"] not in gorulen:
            gorulen.add(k["video_id"])
            out.append({"video_id": k["video_id"], "konu": k.get("konu"), "senaryo": k.get("senaryo"),
                        "profil": k.get("profil"), "yayin": (k.get("yayin_zamani") or k.get("tarih") or "")[:10]})
    for v in kanal_videolari:
        e = basliklar.get(baslik_norm(v.get("baslik")))
        if e and v["video_id"] not in gorulen:
            gorulen.add(v["video_id"])
            out.append({"video_id": v["video_id"], "konu": e[0], "senaryo": e[1], "profil": e[2],
                        "yayin": str(v.get("yayin", ""))[:10]})
    return out


def kanal_videolari(anahtar, requests):
    """Kanalın yüklemeleri listesi (başlık + yayın tarihi)."""
    b = {"Authorization": f"Bearer {anahtar}"}
    r = requests.get(f"{API}/channels", headers=b, timeout=30, params={"part": "contentDetails", "mine": "true"})
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return []
    liste = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    out, sayfa = [], None
    for _ in range(10):
        p = {"part": "snippet", "playlistId": liste, "maxResults": 50}
        if sayfa:
            p["pageToken"] = sayfa
        r = requests.get(f"{API}/playlistItems", headers=b, timeout=30, params=p)
        r.raise_for_status()
        j = r.json()
        for it in j.get("items", []):
            s = it.get("snippet", {})
            vid = s.get("resourceId", {}).get("videoId")
            if vid:
                out.append({"video_id": vid, "baslik": s.get("title", ""), "yayin": s.get("publishedAt", "")})
        sayfa = j.get("nextPageToken")
        if not sayfa:
            break
    return out


def main():
    if not all(os.environ.get(a) for a in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
        ozet("Merak izlenme: kanal anahtarı (MERAK_YT_REFRESH_TOKEN) tanımlı değil, atlandı.")
        return 0
    from cocuk import youtube
    try:
        anahtar = youtube.erisim_anahtari()
        kayitlar = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
        videolar = eslestir(kayitlar, kanal_videolari(anahtar, youtube.requests), senaryo_basliklari())
        ids = [v["video_id"] for v in videolar]
        izl, durum = {}, {}
        for i in range(0, len(ids), 50):
            r = youtube.requests.get(f"{API}/videos", timeout=30, headers={"Authorization": f"Bearer {anahtar}"},
                                     params={"part": "statistics,status", "id": ",".join(ids[i:i + 50])})
            r.raise_for_status()
            for v in r.json().get("items", []):
                izl[v["id"]] = int(v.get("statistics", {}).get("viewCount", 0))
                durum[v["id"]] = v.get("status", {}).get("privacyStatus", "")
    except Exception as e:  # noqa: BLE001 — ölçüm hatası büyüme işini durdurmaz
        ozet(f"Merak izlenme: okunamadı ({type(e).__name__}), rapor değişmedi.")
        return 0
    for v in videolar:
        v["izlenme"] = izl.get(v["video_id"])
        v["durum"] = durum.get(v["video_id"], "silinmiş?")
    videolar.sort(key=lambda v: -(v["izlenme"] or 0))
    RAPOR.write_text(json.dumps({"tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "videolar": videolar}, ensure_ascii=False, indent=1))
    ozet(f"\n### Merak Arşivi izlenmeleri ({len(videolar)} video, toplam {sum(v['izlenme'] or 0 for v in videolar)})")
    for v in videolar:
        ozet(f"- {v['konu']}/{v['senaryo']} ({v['profil']}, {v['yayin']}, {v['durum']}): {v['izlenme']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
