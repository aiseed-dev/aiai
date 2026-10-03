# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runs the aiai site, app and second opinion on this machine, with the fake
Apple and Google of moushikomi/fake_id.py and two fake models. For trying
only; never on a real server.

    python site/make_assets.py
    python site/try.py [--port 8020]
"""
import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "moushikomi"))
sys.path.insert(0, os.path.join(HERE, "..", "soudan"))

if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser(description="偽のサインインと偽のモデルで、aiai のサイトとアプリを試します")
    ap.add_argument("--port", type=int, default=8020)
    ap.add_argument("--fake-port", type=int, default=0, help="偽の Apple と Google のポート(既定は空いている物)")
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}"
    os.environ |= {"AIAI_SOUDAN": base + "/soudan", "AIAI_RETURN": base + "/app/", "AIAI_SITE": base}
    os.environ.setdefault("AIAI_LOCAL", "1")  # trying on one's own PC: show the records tab
    import fake_id
    from fake_model import FakeModel

    sys.path.insert(0, HERE)
    import server as site

    tmp = tempfile.mkdtemp()
    fake, env = fake_id.start(tmp, a.fake_port)
    env |= {"BASE_URL": base + "/soudan", "RETURN_URLS": base + "/app/", "DB": os.path.join(tmp, "try.db"),
            "RESEARCH_EMAILS": "owner@example.jp"}
    soudan = site.load_soudan().create_app(env, models={"試し:A": FakeModel("A"), "試し:B": FakeModel("B")})
    codes = soudan.state.make_invites(3, "試し")
    print(f"{base}/ を開きます。相談のタブで、偽の Apple か Google でサインインします")
    print("試しの招待の番号: " + "、".join(codes))
    uvicorn.run(site.create_app(soudan), host="127.0.0.1", port=a.port)
