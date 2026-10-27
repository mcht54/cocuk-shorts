"""Bir kerelik: YouTube yükleme izni için refresh token alır.

Kullanım: python yetki_al.py client_secret.json
Tarayıcı açılır, kanalın Google hesabıyla izin verilir; çıkan değerler
GitHub Secrets'a (YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN) girilir.
"""
import json
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

PORT = 8765
YONLENDIRME = f"http://127.0.0.1:{PORT}"
# asgari yetki: yalnız yükleme. İzlenme istatistiği için --istatistik ile salt okuma eklenir.
KAPSAM = "https://www.googleapis.com/auth/youtube.upload"
if "--istatistik" in sys.argv:
    KAPSAM += " https://www.googleapis.com/auth/youtube.readonly"
    sys.argv.remove("--istatistik")

bilgi = json.load(open(sys.argv[1]))
bilgi = bilgi.get("installed") or bilgi.get("web")
kod = {}


class Yakala(BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        kod["deger"] = q.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("İzin alındı, bu sekmeyi kapatabilirsiniz.".encode())

    def log_message(self, *a):
        pass


url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": bilgi["client_id"], "redirect_uri": YONLENDIRME, "response_type": "code",
    "scope": KAPSAM, "access_type": "offline", "prompt": "consent"})
print("Tarayıcı açılmazsa bu adresi açın:\n", url)
webbrowser.open(url)
sunucu = HTTPServer(("127.0.0.1", PORT), Yakala)
while not kod:
    sunucu.handle_request()

r = requests.post("https://oauth2.googleapis.com/token", data={
    "code": kod["deger"], "client_id": bilgi["client_id"], "client_secret": bilgi["client_secret"],
    "redirect_uri": YONLENDIRME, "grant_type": "authorization_code"}, timeout=30)
r.raise_for_status()
print("\nYT_CLIENT_ID=" + bilgi["client_id"])
print("YT_CLIENT_SECRET=" + bilgi["client_secret"])
print("YT_REFRESH_TOKEN=" + r.json()["refresh_token"])
