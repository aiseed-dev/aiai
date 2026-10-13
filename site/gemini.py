# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gemini on Google Cloud (Vertex AI), called by REST with the machine's
service account, so no key is kept on the server. Used by the site's
features that run on the server: the guide dialogue and the news of
tameshi/server.py, and the automatic fixes of tools/kaiseki_jidou.py.
Only the standard library is used.

    text, sources = generate(contents, system="...", search=True)
    png = image("スマートフォンの画面の絵 ...")

contents is a list of {"role": "user" | "model", "text": "..."}. With
search=True, Gemini may look things up with Google Search; sources are then
the pages it used, as [(title, url)], with each Google redirect link
followed to the page's own address.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1")
META = "http://metadata.google.internal/computeMetadata/v1/"
_token = {"value": "", "until": 0.0}
_lock = threading.Lock()


class GeminiError(Exception):
    """Gemini gave no usable answer; the message can be shown to the person."""


def _meta(path):
    req = urllib.request.Request(META + path, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode()


def _bearer():
    with _lock:
        if time.time() > _token["until"] - 60:
            d = json.loads(_meta("instance/service-accounts/default/token"))
            _token.update(value=d["access_token"], until=time.time() + d["expires_in"])
        return _token["value"]


def _follow(url):
    """The page a Google Search redirect link leads to (the link itself if it cannot be followed)."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "aiai"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.url
    except (urllib.error.URLError, OSError, ValueError):
        return url


def _post(model, body, timeout):
    try:
        project = _meta("project/project-id")
        url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/"
               f"publishers/google/models/{model}:generateContent")
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {_bearer()}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise GeminiError(f"Gemini が答えませんでした({e.code})") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise GeminiError("Gemini につながりませんでした") from e


def image(prompt, model=None):
    """PNG bytes of one picture drawn from the prompt (Nano Banana unless another model is named)."""
    answer = _post(model or IMAGE_MODEL, {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                          "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}, 300)
    for p in (answer.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        if p.get("inlineData", {}).get("mimeType") == "image/png":
            return base64.b64decode(p["inlineData"]["data"])
    raise GeminiError("絵ができませんでした")


def generate(contents, system="", search=False, schema=None, max_tokens=8192, temperature=0.3, model=None, timeout=180):
    """(text, sources) of one answer. schema, a JSON schema, asks for JSON of that shape."""
    body = {"contents": [{"role": c["role"], "parts": [{"text": c["text"]}]} for c in contents],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if search:
        body["tools"] = [{"google_search": {}}]
    if schema:
        body["generationConfig"] |= {"responseMimeType": "application/json", "responseSchema": schema}
    answer = _post(model or MODEL, body, timeout)
    cands = answer.get("candidates") or [{}]
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise GeminiError("Gemini の答えが空でした")
    sources, seen = [], set()
    for ch in cands[0].get("groundingMetadata", {}).get("groundingChunks", []):
        web = ch.get("web") or {}
        if web.get("uri") and web["uri"] not in seen:
            seen.add(web["uri"])
            sources.append((web.get("title", ""), _follow(web["uri"])))
    return text, sources
