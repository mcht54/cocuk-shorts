"""Yüklenemeyen YouTube kapaklarını (403: kanal telefonla doğrulanmamış) yeniden dener.
Kapaklar kapaklar/<video_id>.jpg'de saklanır; başarılar kapaklar/durum.json'a yazılır. İlk 403'te durur (kanal hâlâ doğrulanmamış).
Kullanım: python kapak_tekrar.py   (YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN)"""
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
KAPAKLAR = KOK / "kapaklar"
DURUM = KAPAKLAR / "durum.json"


def bekleyenler():
    kayit = json.loads((KOK / "yayin_kaydi.json").read_text())
    durum = json.loads(DURUM.read_text()) if DURUM.exists() else {}
    out = []
    for x in kayit:
        vid = x.get("video_id")
        if x.get("profil") == "derleme" and vid and str(x.get("kapak", "")).startswith("yuklenemedi") and durum.get(vid) != "yuklendi" \
                and (KAPAKLAR / f"{vid}.jpg").exists() and vid not in out:
            out.append(vid)
    return out, durum


def main():
    vids, durum = bekleyenler()
    if not vids:
        print("Bekleyen kapak yok.")
        return 0
    from cocuk import youtube
    from derleme import kapak_yukle
    anahtar = youtube.erisim_anahtari()
    for vid in vids:
        kod, metin = kapak_yukle(vid, KAPAKLAR / f"{vid}.jpg", anahtar)
        if kod == 200:
            durum[vid] = "yuklendi"
            print(f"kapak yüklendi: {vid}")
        else:
            print(f"kapak yüklenemedi ({kod}) {vid}: {metin[:160]}")
            if kod == 403:
                print("Kanal hâlâ doğrulanmamış (youtube.com/verify); diğerleri denenmedi.")
                break
    KAPAKLAR.mkdir(exist_ok=True)
    DURUM.write_text(json.dumps(durum, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
