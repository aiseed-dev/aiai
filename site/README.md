# aiai のサイトとアプリ

| ファイル | 中身 |
|---|---|
| `index.html`、`top.css` | トップページと、全部のページの見た目。手で書いた HTML と CSS だけで、外の書体や部品は読み込みません。トップページの `<!-- news -->` の所に、`make_site.py` が新しいニュースを入れます |
| `make_site.py` | Web のページを `public/` に作ります。トップページ、スキルごとのページ(中身、「写す」、ZIP)、考え方(`app/assets/kangaekata.md`)、ニュース(`news/*.adoc`)。`public/` はリポジトリに入れません。標準ライブラリだけ |
| `test_site.py` | `make_site.py` の確かめ |
| `app/main.py` | Flet の画面。スキルの一覧(開いて「写す」で写し、自分の AI に貼る)、考え方、お知らせ、相談の 4 つのタブ。同じコードを `flet build` で iPhone と Android のアプリにする予定です |
| `app/soudan_view.py` | 相談のタブ。`soudan/server.py` と話します |
| `app/kiroku.py`、`app/kiroku_view.py` | 記録のタブ。PC の AI の道具の記録や、書き出したファイルから、本人の発言だけを機械的に読み、識別情報に見える物を伏せて、報告書の AI エージェントに渡します。本人の PC で動かすとき(`AIAI_LOCAL=1`)だけ出ます。標準ライブラリだけ |
| `app/server_view.py` | サーバーのタブ。本人の PC で動かすときだけ。サーバーが毎日 0 時 5 分に `tools/kougeki.py` で書く攻撃の記録(SSH の試み、穴を探す HTTP の要求、開いている口、Gemini の所見)を、SSH で `~/aiai-server/` に取り込み、日ごとに並べて見せる。サーバーは `AIAI_SERVER`(`dev@example.jp`)で決める |
| `app/news_adoc.py`、`app/news_view.py` | ニュースのタブ。本人の PC で動かすとき(`AIAI_LOCAL=1`)だけ。`news/tsukuru.py` で AI の CLI に今日の下書きを書かせ、記事ごとに残す・消す・直すをして adoc に保存し、`news/好み.adoc` も直す。ほかでは「お知らせ」として読むだけ |
| `test_kiroku.py` | 記録の読み方の確かめ |
| `app/assets/` | アプリが持ち歩く物。`kangaekata.md`(考え方)、`news/*.adoc`(お知らせ)、`skills/`(各フォルダーの `SKILL.md` の写し。`make_assets.py` が作り、リポジトリには入れません) |
| `make_assets.py` | 各フォルダーの `SKILL.md` を `app/assets/skills/` に写します。標準ライブラリだけ |
| `server.py` | `/` で `public/` のページ、`/skills/<名前>.zip` でスキルの ZIP、`/app/` で Flet の画面、`SOUDAN_MODELS` があれば `/soudan/` でセカンドオピニオンのサーバーを出します |
| `try.py` | 偽の Apple と Google と、偽のモデル 2 つで、全部を手元で立てます。試すためだけの物です |

## 動かす

部品は `moushikomi/` と同じです(conda-forge の `fastapi`、`uvicorn`、`pyjwt`、`cryptography`、
`python-multipart`、`websockets`、`flet`、pip の `flet-web`)。

```
python site/make_assets.py
python site/make_site.py
python site/try.py
```

Web のページは、考え方と使い方を短く、図で見せる所です。細かくやらないといけない作業(記録を読む、
ニュースを作って直す、サーバーの記録を見る、相談)は、Flet のアプリでします。詳しいことは、手引きを
読ませた本人の AI に聞きます。

`http://127.0.0.1:8020/` を開きます。ほかの機械で立てて SSH で転送して見るときは、
`--fake-port 8021` のように、偽の Apple と Google のポートも決めておくと、転送する先が変わりません。相談のタブでは、偽の Apple か Google でサインインし、
`try.py` が表示する試しの招待の番号を入れます。

本物で動かすときは、`soudan/README.md` の設定(`BASE_URL` は `/soudan` で終わる物)と、
`app/soudan_view.py` の `AIAI_SOUDAN`、`AIAI_SOUDAN_API`、`AIAI_RETURN` を環境の変数で渡して、
`python site/server.py` を動かします。

## いまの状態

- deb2 の dev のホームで動かし、ブラウザーで押して確かめました(2026-10-02)。トップページ
  (スマートフォンの幅と広い幅、明るい画面と暗い画面)、アプリの最初の画面、3 つのタブ、「写す」、
  相談のタブのサインインから、評価、出来事、記録をすべて消すまで
- https://aiai.aiseed.dev/ で公開しています(2026-10-04)。Google Cloud の Compute Engine の VM
  (Debian 13)で、`site/server.py` を systemd(`aiai-site`)で動かし、Caddy の後ろに置いています。
  Caddy は同じ VM のほかの Web と共有するので、aiai の分は `/etc/caddy/aiai.caddy` に分けています。
  トップページ、スキルの ZIP、アプリの最初の画面が開くことを、外から確かめました
- `flet build` でのアプリへの書き出しは、まだです
- `genba/` の記録の画面は、まだありません
