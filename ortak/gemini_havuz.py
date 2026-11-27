"""Gemini ücretsiz anahtar havuzu (ortak modül, yalnız standart kütüphane).

Bu dosya hatlara aynen kopyalanır (Muhit, Mchttasarım, Yorumdan, IG Otopilot, Dijital Çırak, Çocuk Shorts).
Bir kopyada değişiklik yaparsan diğerlerine de taşı; SURUM'u artır.

Kural (kullanıcı kararı): YALNIZ ÜCRETSİZ katman. Ödeme hesabı bağlanmaz, ücretli plana geçilmez. Kota dolunca
ücretliye değil, BAŞKA BİR ÜCRETSİZ anahtara (ayrı Gmail hesabının ayrı projesi) geçilir; hepsi doluysa çağıran
kendi yedeğine (Groq / kural metni / edge-tts) düşer.

Anahtarlar: ortam değişkenleri ve (verildiyse) .env dosyası — GEMINI_API_KEY, GEMINI_API_KEY_1 … GEMINI_API_KEY_9
ve virgülle ayrılmış GEMINI_API_KEYS. Sıra korunur, tekrarlar atılır. Boş değerler yok sayılır.

Dolu işareti: günlük kota (429 + quotaId '…PerDay…' / 'per day' / 'limit: 0') gelen anahtar o MODEL için o Google
günü boyunca (Pasifik gece yarısına = TR 11:00'e kadar) "dolu" yazılır. Metin ve TTS modelleri ayrı kotadır: işaret
model × anahtar bazındadır. Durum dosyasında anahtarın kendisi DEĞİL, sha256 parmak izinin ilk 8 karakteri tutulur.
Geçersiz anahtar (API_KEY_INVALID vb.) o gün tüm modellerde atlanır. Dakikalık 429 ve 5xx'te kısa beklenip yeniden
denenir; dakikalık sınır sürerse işaretlenmeden sıradaki anahtara geçilir.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request

SURUM = "1.0 (2026-11-28)"
API = "https://generativelanguage.googleapis.com/v1beta"
ADLAR = ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(1, 10)]
COKLU_AD = "GEMINI_API_KEYS"
DURUM_ORTAM = "GEMINI_HAVUZ_DOSYASI"   # testler/özel kurulum için durum dosyası yolunu ezer


class GunlukKota(RuntimeError):
    """Bu model için havuzdaki bütün anahtarların bugünkü ücretsiz kotası dolu (TR 11:00'de yenilenir)."""


class GeminiHatasi(RuntimeError):
    """Kota dışı hata (model yok, istek bozuk, geçici hata sürdü, anahtar yok). kod: HTTP kodu ya da None."""

    def __init__(self, mesaj: str, kod: int | None = None):
        super().__init__(mesaj)
        self.kod = self.code = kod   # .code: eski HTTPError yakalayan kodlarla uyum


class AnahtarYok(GeminiHatasi):
    """Hiç Gemini anahtarı tanımlı değil."""


# ---------------------------------------------------------------- anahtarlar

def _env_dosyasi_oku(yol) -> dict:
    sonuc = {}
    try:
        p = pathlib.Path(yol)
        if not p.exists():
            return sonuc
        for satir in p.read_text(errors="ignore").splitlines():
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            ad, _, deger = satir.partition("=")
            ad = ad.strip().removeprefix("export ").strip()
            sonuc.setdefault(ad, deger.strip())
    except OSError:
        pass
    return sonuc


def anahtarlar(ortam=None, env_dosyasi=None) -> list[str]:
    """Havuzdaki anahtarlar (önce ortam, sonra .env dosyası), sırası korunmuş ve tekrarsız."""
    ortam = os.environ if ortam is None else ortam
    kaynaklar = [ortam] + ([_env_dosyasi_oku(env_dosyasi)] if env_dosyasi else [])
    ks: list[str] = []

    def ekle(deger):
        for parca in re.split(r"[,\s;]+", deger or ""):
            parca = parca.strip().strip("'\"")
            if parca and parca not in ks:
                ks.append(parca)

    for kaynak in kaynaklar:
        for ad in ADLAR:
            ekle(kaynak.get(ad, ""))
        ekle(kaynak.get(COKLU_AD, ""))
    return ks


def parmak(anahtar: str) -> str:
    """Anahtarın parmak izi (sha256 ilk 8 karakter) — sır değildir, kayıtlarda anahtar yerine bu yazılır."""
    return hashlib.sha256(anahtar.encode()).hexdigest()[:8]


def google_gunu(simdi: dt.datetime | None = None) -> str:
    """Google ücretsiz kotasının günü: Pasifik saatiyle tarih (kış TR 11:00'de, yaz TR 10:00'da değişir)."""
    simdi = simdi or dt.datetime.now(dt.timezone.utc)
    if simdi.tzinfo is None:
        simdi = simdi.replace(tzinfo=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
    except Exception:  # noqa: BLE001  (tzdata yoksa kış saati varsayılır)
        tz = dt.timezone(dt.timedelta(hours=-8))
    return simdi.astimezone(tz).date().isoformat()


# ---------------------------------------------------------------- 429 çözümleme

def kota_bilgisi(metin: str) -> dict:
    """429 gövdesinden yalnız quotaId ve retryDelay (gövde/anahtar kaydedilmez).
    gunluk: True (günlük/limit 0), False (dakikalık), None (anlaşılamadı)."""
    kimlik, bekle = [], None
    try:
        hata = json.loads(metin or "").get("error", {})
        hata = hata if isinstance(hata, dict) else {}
        for d in hata.get("details") or []:
            tur = str(d.get("@type", ""))
            if tur.endswith("QuotaFailure"):
                kimlik += [str(v.get("quotaId", ""))[:120] for v in d.get("violations") or [] if v.get("quotaId")]
            elif tur.endswith("RetryInfo"):
                bekle = str(d.get("retryDelay") or "")[:20] or None
    except Exception:  # noqa: BLE001
        pass
    duz = (metin or "").lower().replace(" ", "")
    if any("PerDay" in k for k in kimlik) or "perday" in duz or "daily" in duz or "limit:0," in duz or "limit:0\"" in duz:
        gunluk = True
    elif any("PerMinute" in k for k in kimlik) or "perminute" in duz:
        gunluk = False
    else:
        gunluk = None
    sn = None
    if bekle:
        m = re.match(r"([\d.]+)", bekle)
        sn = float(m.group(1)) if m else None
    return {"gunluk": gunluk, "kota": ",".join(kimlik) or None, "bekle": bekle, "bekle_sn": sn}


def _kota_ozet(b: dict) -> str:
    parca = [f"quotaId={b['kota']}"] if b.get("kota") else []
    if b.get("bekle"):
        parca.append(f"retryDelay={b['bekle']}")
    return " ".join(parca) or "ayrıntı yok"


_GECERSIZ = ("API_KEY_INVALID", "API key not valid", "API_KEY_EXPIRED", "API key expired", "CONSUMER_SUSPENDED",
             "has been suspended", "API_KEY_SERVICE_BLOCKED", "SERVICE_DISABLED")


def _hata_ozet(metin: str) -> str:
    try:
        return str(json.loads(metin)["error"].get("status") or "")[:40]
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- taşıyıcı

def urllib_gonder(model: str, govde: dict, anahtar: str, zaman: float, yol: str = "generateContent"):
    """Varsayılan taşıyıcı. (HTTP kodu, gövde metni) döner; ağ hatasında OSError/TimeoutError fırlatır."""
    req = urllib.request.Request(f"{API}/models/{model}:{yol}", data=json.dumps(govde).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": anahtar})
    try:
        with urllib.request.urlopen(req, timeout=zaman) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            govde_metni = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            govde_metni = ""
        return e.code, govde_metni


# ---------------------------------------------------------------- havuz

class Havuz:
    """Anahtar havuzu. durum_yolu: dolu işaretlerinin JSON dosyası (None → yalnız bu süreçte tutulur).
    anahtar_kaynagi: liste ya da liste döndüren fonksiyon (varsayılan: anahtarlar()).
    gonder(model, govde, anahtar, zaman, yol) -> (kod, metin): test için sahte taşıyıcı verilebilir."""

    def __init__(self, durum_yolu=None, anahtar_kaynagi=None, gunluk=None, gonder=None, uyku=None, saat=None):
        ezme = os.environ.get(DURUM_ORTAM)
        self.yol = pathlib.Path(ezme) if ezme else (pathlib.Path(durum_yolu) if durum_yolu else None)
        self._kaynak = anahtar_kaynagi
        self.gunluk = gunluk or (lambda m: print(m, flush=True))
        self.gonder = gonder or urllib_gonder
        self.uyku = uyku or time.sleep
        self.saat = saat or (lambda: dt.datetime.now(dt.timezone.utc))
        self._yerel: dict = {"gun": None, "dolu": {}}

    # --- anahtarlar
    def anahtarlar(self) -> list[str]:
        k = self._kaynak
        if k is None:
            return anahtarlar()
        return list(k() if callable(k) else k)

    def sayi(self) -> int:
        return len(self.anahtarlar())

    # --- durum dosyası
    def gun(self) -> str:
        return google_gunu(self.saat())

    def _oku_yaz(self, degistir=None) -> dict:
        """Kilitli oku(-değiştir-yaz). Gün değiştiyse işaretler sıfırlanır. Dosya yazılamazsa süreç içi kopya kullanılır."""
        gun = self.gun()
        if self._yerel.get("gun") != gun:
            self._yerel = {"gun": gun, "dolu": {}}
        if self.yol is None:
            if degistir:
                degistir(self._yerel)
            return self._yerel
        try:
            import fcntl
        except ImportError:  # noqa: BLE001
            fcntl = None
        try:
            self.yol.parent.mkdir(parents=True, exist_ok=True)
            with open(self.yol, "a+") as f:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                try:
                    v = json.loads(f.read() or "{}")
                    v = v if isinstance(v, dict) else {}
                except ValueError:
                    v = {}
                eski = json.dumps(v, sort_keys=True)
                if v.get("gun") != gun:
                    v = {"gun": gun, "dolu": {}}
                v.setdefault("dolu", {})
                for a, b in self._yerel["dolu"].items():   # dosyaya yazılamamış süreç içi işaretleri de taşı
                    v["dolu"].setdefault(a, b)
                if degistir:
                    degistir(v)
                if json.dumps(v, sort_keys=True) != eski:
                    f.seek(0)
                    f.truncate()
                    f.write(json.dumps(v, ensure_ascii=False, indent=1, sort_keys=True))
                    f.flush()
                    os.fsync(f.fileno())
                self._yerel = {"gun": gun, "dolu": dict(v["dolu"])}
                return v
        except OSError as e:
            self.gunluk(f"gemini havuz: durum dosyası kullanılamadı ({type(e).__name__}); işaretler yalnız bu süreçte")
            if degistir:
                degistir(self._yerel)
            return self._yerel

    @staticmethod
    def _ad(model: str, anahtar: str) -> str:
        return f"{model}|{parmak(anahtar)}"

    def dolu_mu(self, model: str, anahtar: str, durum: dict | None = None) -> bool:
        d = (durum or self._oku_yaz())["dolu"]
        return self._ad(model, anahtar) in d or self._ad("*", anahtar) in d

    def isaretle(self, model: str, anahtar: str, neden: str = "gunluk") -> None:
        zaman = self.saat().astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._oku_yaz(lambda v: v["dolu"].__setitem__(self._ad(model, anahtar), f"{neden} {zaman}"))

    def bos_anahtarlar(self, model: str) -> list[str]:
        durum = self._oku_yaz()
        return [k for k in self.anahtarlar() if not self.dolu_mu(model, k, durum)]

    def hepsi_dolu(self, model: str) -> bool:
        return bool(self.anahtarlar()) and not self.bos_anahtarlar(model)

    def ozet(self) -> dict:
        """Panel/nabız için: gün, anahtar sayısı, parmak izleri, dolu işaretleri (sır yok)."""
        durum = self._oku_yaz()
        return {"gun": durum["gun"], "anahtar_sayisi": self.sayi(),
                "parmaklar": [parmak(k) for k in self.anahtarlar()], "dolu": dict(durum["dolu"])}

    # --- çağrı
    def cagir(self, model: str, govde: dict, zaman: float = 180, deneme: int = 3, yol: str = "generateContent") -> dict:
        """Boş anahtarları sırayla dener. Başarıda yanıt JSON'u döner.
        Hepsi günlük doluysa GunlukKota; kota dışı hata / sürmüş geçici hata / dakikalık sınırda GeminiHatasi."""
        ks = self.anahtarlar()
        if not ks:
            raise AnahtarYok("GEMINI_API_KEY tanımlı değil")
        sira = {k: i + 1 for i, k in enumerate(ks)}
        bos = self.bos_anahtarlar(model)
        if not bos:
            raise GunlukKota(f"{model}: {len(ks)} anahtarın hepsinin bugünkü ücretsiz kotası dolu (TR 11:00'de yenilenir)")
        deneme = max(1, int(deneme))
        isaretsiz_kaldi = None       # dakikalık sınır yüzünden işaretlenmeden atlanan anahtar varsa son hata
        for k in bos:
            etiket = f"anahtar {sira[k]}/{len(ks)} [{parmak(k)}]"
            for i in range(deneme):
                try:
                    kod, metin = self.gonder(model, govde, k, zaman, yol)
                except (TimeoutError, OSError) as e:   # urllib.error.URLError ve requests hataları OSError'dır
                    kod, metin = None, type(e).__name__
                if kod is not None and 200 <= kod < 300:
                    try:
                        return json.loads(metin)
                    except ValueError as e:
                        raise GeminiHatasi(f"{model}: yanıt JSON değil", kod) from e
                if kod == 429:
                    b = kota_bilgisi(metin)
                    if b["gunluk"] is True or (b["gunluk"] is None and i == deneme - 1):
                        self.isaretle(model, k, "gunluk" if b["gunluk"] else "429")
                        self.gunluk(f"gemini {model} HTTP 429 ({_kota_ozet(b)}): {etiket} günlük kotası doldu, "
                                    f"bugün (TR 11:00'e kadar) bu modelde atlanır")
                        break
                    if i < deneme - 1:
                        bekle = min(max(b["bekle_sn"] or 10 * (i + 1), 5), 60)
                        self.gunluk(f"gemini {model} HTTP 429 ({_kota_ozet(b)}): {etiket} dakikalık sınır, {bekle:.0f} sn bekleniyor")
                        self.uyku(bekle)
                        continue
                    isaretsiz_kaldi = GeminiHatasi(f"{model}: dakikalık sınır sürdü", 429)
                    self.gunluk(f"gemini {model}: {etiket} dakikalık sınırı sürdü, sıradaki anahtara geçiliyor")
                    break
                if kod in (400, 401, 403) and any(x in (metin or "") for x in _GECERSIZ):
                    self.isaretle("*", k, f"gecersiz-{kod}")
                    self.gunluk(f"gemini {model} HTTP {kod} {_hata_ozet(metin)}: {etiket} geçersiz/engelli, bugün atlanır")
                    break
                if kod is None or kod in (408, 500, 502, 503, 504):
                    if i < deneme - 1:
                        bekle = (5, 15, 30)[min(i, 2)]
                        self.gunluk(f"gemini {model} geçici hata ({kod or metin}), {bekle} sn sonra tekrar")
                        self.uyku(bekle)
                        continue
                    raise GeminiHatasi(f"{model}: geçici hata sürdü ({kod or metin})", kod)
                raise GeminiHatasi(f"{model} HTTP {kod} {_hata_ozet(metin)}".strip(), kod)
        if isaretsiz_kaldi is not None and not self.hepsi_dolu(model):
            raise isaretsiz_kaldi
        raise GunlukKota(f"{model}: tüm anahtarların ({len(ks)}) bugünkü ücretsiz kotası doldu (TR 11:00'de yenilenir)")


def requests_gonder_yap(requests_modulu_al):
    """requests kullanan hatlar için taşıyıcı üretir. requests_modulu_al: çağrı anında requests modülünü döndüren
    fonksiyon (testlerdeki monkeypatch'ler böylece geçerli kalır)."""
    def gonder(model, govde, anahtar, zaman, yol="generateContent"):
        r = requests_modulu_al().post(f"{API}/models/{model}:{yol}", headers={"x-goog-api-key": anahtar},
                                      json=govde, timeout=zaman)
        return r.status_code, (getattr(r, "text", "") or "")
    return gonder
