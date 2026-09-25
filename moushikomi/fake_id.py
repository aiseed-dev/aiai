# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fake Apple and Google sign-in, for trying server.py and the screen on this
machine without real accounts. Never use it on a real server.

    python fake_id.py 取り置き.koumoku.adoc      (server + screen + fake sign-in)

It serves both providers' discovery documents and keys, checks the client
secret (Apple's as an ES256 JWT), and answers a code with an id_token signed
by its own RSA key. Its sign-in page asks for nothing: it shows a button per
made-up person, and sends the answer back the way the real one does (a POST
for Apple, a redirect for Google).

The code carries, as JSON, what to put in the id_token; test_server.py uses
that to also hand out broken ones (wrong nonce, audience, expired, other key).
"""
import base64
import html
import http.server
import json
import os
import tempfile
import threading
import time
import urllib.parse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
APPLE_P8 = ec.generate_private_key(ec.SECP256R1())
TEAM, KEY_ID, SERVICES_ID = "TEAM123", "KEY123", "jp.example.hanako.web"
GOOGLE_ID, GOOGLE_SECRET = "google-client", "google-secret"
PEOPLE = [("hana", "hana@example.jp"), ("taro", "taro@example.jp"), ("owner", "owner@example.jp")]
seen_secrets = []


def code(nonce, sub, email="", **extra):
    return base64.urlsafe_b64encode(json.dumps({"nonce": nonce, "sub": sub, "email": email, **extra}).encode()).decode()


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, status=200, kind="application/json"):
        data = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def issuer(self, name):
        return f"http://127.0.0.1:{self.server.server_port}/{name}"

    def do_GET(self):
        path, _, query = self.path.partition("?")
        name, _, rest = path.strip("/").partition("/")
        if rest == ".well-known/openid-configuration":
            iss = self.issuer(name)
            return self.send({"issuer": iss, "authorization_endpoint": iss + "/auth",
                              "token_endpoint": iss + "/token", "jwks_uri": iss + "/keys"})
        if rest == "keys":
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(RSA_KEY.public_key()))
            return self.send({"keys": [jwk | {"kid": "k1", "alg": "RS256", "use": "sig"}]})
        if rest == "auth":
            return self.sign_in_page(name, dict(urllib.parse.parse_qsl(query)))
        self.send({}, 404)

    def sign_in_page(self, name, q):
        # One button per made-up person; Apple answers with a POST, Google with a redirect
        buttons = []
        for sub, email in PEOPLE:
            c = code(q.get("nonce", ""), f"{name}-{sub}", email)
            if q.get("response_mode") == "form_post":
                buttons.append(
                    f'<form method="post" action="{html.escape(q["redirect_uri"])}">'
                    f'<input type="hidden" name="code" value="{c}">'
                    f'<input type="hidden" name="state" value="{html.escape(q.get("state", ""))}">'
                    f'<button>{email}</button></form>')
            else:
                url = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": c, "state": q.get("state", "")})
                buttons.append(f'<p><a href="{html.escape(url)}">{email}</a></p>')
        self.send(f"<!doctype html><meta charset=utf-8><title>偽の {name}</title>"
                  f"<h1>偽の {name} のサインイン(試すためだけの物)</h1>{''.join(buttons)}",
                  kind="text/html; charset=utf-8")

    def do_POST(self):
        name, _, rest = self.path.strip("/").partition("/")
        form = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode()))
        seen_secrets.append((name, form.get("client_secret")))
        iss = self.issuer(name)
        if name == "apple":
            try:  # Apple's client secret: an ES256 JWT for this Services ID
                c = jwt.decode(form["client_secret"], APPLE_P8.public_key(), algorithms=["ES256"],
                               audience=iss)
                assert c["iss"] == TEAM and c["sub"] == form["client_id"] == SERVICES_ID
                assert jwt.get_unverified_header(form["client_secret"])["kid"] == KEY_ID
            except Exception:
                return self.send({"error": "invalid_client"}, 400)
        elif form.get("client_secret") != GOOGLE_SECRET:
            return self.send({"error": "invalid_client"}, 400)
        spec = json.loads(base64.urlsafe_b64decode(form["code"]))
        now = int(time.time())
        claims = {"iss": iss, "aud": form["client_id"], "sub": spec["sub"], "iat": now, "exp": now + 600,
                  "nonce": spec["nonce"], "email": spec.get("email", ""), "email_verified": True}
        claims |= spec.get("override", {})
        key = OTHER_KEY if spec.get("other_key") else RSA_KEY
        self.send({"id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})})


def start(folder):
    """Starts the fake; returns it and the settings server.py needs to use it."""
    fake = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    key_file = os.path.join(folder, "AuthKey.p8")
    with open(key_file, "wb") as f:
        f.write(APPLE_P8.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    port = fake.server_port
    env = {"GOOGLE_CLIENT_ID": GOOGLE_ID, "GOOGLE_CLIENT_SECRET": GOOGLE_SECRET,
           "GOOGLE_ISSUER": f"http://127.0.0.1:{port}/google",
           "APPLE_SERVICES_ID": SERVICES_ID, "APPLE_TEAM_ID": TEAM, "APPLE_KEY_ID": KEY_ID,
           "APPLE_KEY_FILE": key_file, "APPLE_ISSUER": f"http://127.0.0.1:{port}/apple"}
    return fake, env


if __name__ == "__main__":
    import argparse

    import uvicorn

    import server

    ap = argparse.ArgumentParser(description="偽のサインインで、申し込みのサーバーと画面を手元で試します")
    ap.add_argument("koumoku")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp()
    fake, env = start(tmp)
    base = f"http://127.0.0.1:{a.port}"
    env |= {"BASE_URL": base, "RETURN_URLS": base + "/app/", "DB": os.path.join(tmp, "try.db"),
            "SHOP_EMAILS": "owner@example.jp"}
    web = server.create_app(a.koumoku, env)
    server.mount_screen(web, base)
    print(f"{base}/app/ を開きます。店の人として試すときは owner@example.jp を選びます")
    uvicorn.run(web, host="127.0.0.1", port=a.port)
