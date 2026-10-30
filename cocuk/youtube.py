"""YouTube Data API v3: yükleme ve izlenme sayısı okuma (google kütüphanesi gerektirmez)."""
import os

import requests


def erisim_anahtari():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


GIZLILIKLER = ("private", "unlisted", "public")


class OnaySiz(PermissionError):
    """Herkese açık/liste dışı yükleme açık kullanıcı onayı olmadan istendi."""


def yukle(dosya, senaryo, anahtar, gizlilik="private", acik_onay=False, shorts=True, sentetik=True,
          cocuklar=True, kategori="27", hazir_aciklama=False):
    """Videoyu yükler; (video_id, YouTube'un döndürdüğü gerçek status) verir.

    gizlilik her zaman açıkça gönderilir (varsayılana güvenilmez). private dışı her değer
    acik_onay=True ister; zamanlanmış herkese açık yayın (publishAt) hiç desteklenmez.
    """
    if gizlilik not in GIZLILIKLER:
        raise ValueError(f"geçersiz gizlilik: {gizlilik}")
    if gizlilik != "private" and not acik_onay:
        raise OnaySiz(f"'{gizlilik}' yükleme için ayrı, açık kullanıcı onayı gerekli")
    baslik = senaryo["baslik"][:90]
    if shorts and "#shorts" not in baslik.lower():
        baslik = (baslik + " #shorts")[:100]
    aciklama = (senaryo.get("aciklama", "") + "\n\n"
                + " ".join("#" + e.replace(" ", "") for e in senaryo.get("etiketler", [])[:5]))
    if hazir_aciklama:  # açıklama zaten tam (bölüm zamanları, kaynaklar): olduğu gibi gönder
        aciklama = senaryo["aciklama"]
    govde = {
        "snippet": {
            "title": baslik,
            "description": aciklama[:4900],
            "tags": senaryo.get("etiketler", [])[:15],
            "categoryId": kategori,  # 27 = Eğitim
            "defaultLanguage": "tr",
            "defaultAudioLanguage": "tr",
        },
        "status": {
            "privacyStatus": gizlilik,
            "selfDeclaredMadeForKids": cocuklar,  # Minik Masal Evi: 3-7 yaş (COPPA); Merak Arşivi: hayır
            "containsSyntheticMedia": sentetik,
            "embeddable": True,
        },
    }
    basla = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {anahtar}",
                 "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(os.path.getsize(dosya))},
        json=govde, timeout=60)
    basla.raise_for_status()
    with open(dosya, "rb") as f:
        r = requests.put(basla.headers["Location"], data=f,
                         headers={"Content-Type": "video/mp4"}, timeout=600)
    r.raise_for_status()
    v = r.json()
    st = v.get("status", {})
    return v["id"], {k: st.get(k) for k in ("privacyStatus", "uploadStatus", "selfDeclaredMadeForKids")}


def durum(video_id, anahtar):
    """Yükleme sonrası gerçek yayın durumu (privacyStatus, uploadStatus, madeForKids)."""
    r = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
        "part": "status", "id": video_id},
        headers={"Authorization": f"Bearer {anahtar}"}, timeout=30)
    r.raise_for_status()
    ogeler = r.json().get("items", [])
    if not ogeler:
        return {"privacyStatus": None, "not": "video listede yok"}
    st = ogeler[0]["status"]
    return {k: st.get(k) for k in ("privacyStatus", "uploadStatus", "rejectionReason",
                                   "failureReason", "madeForKids", "selfDeclaredMadeForKids")}


def izlenmeler(video_idleri, anahtar):
    """{video_id: izlenme} — 50'lik gruplar halinde, grup başına 1 kota birimi."""
    sonuc = {}
    for i in range(0, len(video_idleri), 50):
        r = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
            "part": "statistics", "id": ",".join(video_idleri[i:i + 50])},
            headers={"Authorization": f"Bearer {anahtar}"}, timeout=30)
        r.raise_for_status()
        for v in r.json().get("items", []):
            sonuc[v["id"]] = int(v["statistics"].get("viewCount", 0))
    return sonuc
