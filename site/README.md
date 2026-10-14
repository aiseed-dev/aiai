# aiai のサイトとアプリ

| ファイル | 中身 |
|---|---|
| `index.html`、`top.css` | トップページと、全部のページの見た目。手で書いた HTML と CSS だけで、外の書体や部品は読み込みません。流れ(`<!-- flow -->` から `<!-- /flow -->` まで)は、`make_site.py` が使い方のページにも入れます。足もとは、`make_site.py` の物に替わります |
| `make_site.py` | Web のページを `public/` に作ります。トップページ、手引きごとのページ(頭の文は `README.md` の初めの段落、中身、「写す」、ZIP)、使い方(利用者マニュアル `tameshi/docs/manual.adoc` から)、紹介(`shoukai/*.adoc`)、考え方(`app/assets/kangaekata.md`)、記事(`kiji/*.md`)、ニュース(`news/*.adoc`)、探す、読まれ方の記録と直し方の記録、検索の目録(`sagasu.json`)、見つからないページ。`public/` はリポジトリに入れません。標準ライブラリだけ |
| `test_site.py` | `make_site.py` の確かめ |
| `test_app.py`、`test_tameshi_view.py` | アプリの立ち上がりの題と、「作る」のタブの道の確かめ(Flet と FastAPI がある所で動く) |
| `app/main.py` | Flet の画面。手引き(一覧。開いて「スキルをコピー」でコピーし、自分の AI に貼る)、作る、使い方、考え方、お知らせ、相談のタブ。中身の幅は、PC で 960 px までです。同じコードを `flet build` で iPhone と Android のアプリにする予定です |
| `app/tameshi_view.py` | 作るのタブ。流れの 2、3、5、6、8 と、手引きを読ませた Gemini との対話、今日のニュースの欄。`tameshi/server.py` の API と話します |
| `app/manual_view.py` | 使い方のタブ。利用者マニュアル(`app/assets/manual/`)を出します |
| `app/glyphs.py` | Web のアプリで日本語の字が抜けないよう、タブを初めて出すときに、使う字を先に読み込みます |
| `app/kaiseki_view.py` | 解析のタブ。本人の PC で動かすときだけ。毎日のまとめを SSH で取り込み、`kaiseki/naosu.py` で本人の AI の CLI にサイトを直させます(別の枝で、取り込むかは本人が決める) |
| `app/soudan_view.py` | 相談のタブ。`soudan/server.py` と話します |
| `app/kiroku.py`、`app/kiroku_view.py` | 記録のタブ。PC の AI の道具の記録や、書き出したファイルから、本人の発言だけを機械的に読み、識別情報に見える物を伏せて、報告書の AI エージェントに渡します。本人の PC で動かすとき(`AIAI_LOCAL=1`)だけ出ます。標準ライブラリだけ |
| `app/server_view.py` | サーバーのタブ。本人の PC で動かすときだけ。サーバーが毎日 0 時 5 分に `tools/kougeki.py` で書く攻撃の記録(SSH の試み、穴を探す HTTP の要求、開いている口、Gemini の所見)を、SSH で `~/aiai-server/` に取り込み、日ごとに並べて見せる。サーバーは `AIAI_SERVER`(`dev@example.jp`)で決める |
| `app/news_adoc.py`、`app/news_view.py` | ニュースのタブ。本人の PC で動かすとき(`AIAI_LOCAL=1`)だけ。`news/tsukuru.py` で AI の CLI に今日の下書きを書かせ、記事ごとに残す・消す・直すをして adoc に保存し、`news/好み.adoc` も直す。ほかでは「お知らせ」として読むだけ |
| `test_kiroku.py` | 記録の読み方の確かめ |
| `app/assets/` | アプリが持ち歩く物。`kangaekata.md`(考え方)、`news/*.adoc`(お知らせ)、`skills/`(各フォルダーの `SKILL.md` の写し。`make_assets.py` が作り、リポジトリには入れません) |
| `make_assets.py` | 各フォルダーの `SKILL.md` を `app/assets/skills/` に写します。標準ライブラリだけ |
| `server.py` | `/` で `public/` のページ、`/skills/<名前>.zip` で手引きの ZIP、`/app/` で Flet の画面、`AIAI_TAMESHI=1` なら `/tameshi` で「作る」の API(`tameshi/server.py`)、`AIAI_SAGASU=vertex` なら `/api/sagasu` でサイトの中の検索(Gemini が目録の番号を選ぶだけ)、`SOUDAN_MODELS` があれば `/soudan/` でセカンドオピニオンのサーバーを出します。`/katsuyou.html` は `/tsukaikata.html` へ送ります |
| `gemini.py` | Vertex AI の Gemini を、VM のサービスアカウントで呼びます(鍵を置かない)。標準ライブラリだけ |
| `sagasu.js`、`kaiseki-aiai.js` | 探すのページのスクリプトと、aiai の出来事(読んだ見出し、押したリンクなど)を kaiseki に送るスクリプト |
| `figures/` | 考え方のページの図(SVG) |
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

アプリは AGPL-3.0-or-later で公開しているので、自分の仕事に合わせて直して使えます。直すのは、本人と
本人の AI です。直した物を人に使わせるときは、AGPL のとおり、直したソースも公開します。

`http://127.0.0.1:8020/` を開きます。ほかの機械で立てて SSH で転送して見るときは、
`--fake-port 8021` のように、偽の Apple と Google のポートも決めておくと、転送する先が変わりません。相談のタブでは、偽の Apple か Google でサインインし、
`try.py` が表示する試しの招待の番号を入れます。

本物で動かすときは、`soudan/README.md` の設定(`BASE_URL` は `/soudan` で終わる物)と、
`app/soudan_view.py` の `AIAI_SOUDAN`、`AIAI_SOUDAN_API`、`AIAI_RETURN` を環境の変数で渡して、
`python site/server.py` を動かします。

## いまの状態

- deb2 の dev のホームで動かし、ブラウザーで押して確かめました(2026-10-02)。トップページ
  (スマートフォンの幅と広い幅、明るい画面と暗い画面)、アプリの最初の画面、3 つのタブ、「コピー」、
  相談のタブのサインインから、評価、出来事、記録をすべて消すまで
- https://aiai.aiseed.dev/ で公開しています(2026-10-04)。Google Cloud の Compute Engine の VM
  (Debian 13)で、`site/server.py` を systemd(`aiai-site`)で動かし、Caddy の後ろに置いています。
  Caddy は同じ VM のほかの Web と共有するので、aiai の分は `/etc/caddy/aiai.caddy` に分けています。
  トップページ、スキルの ZIP、アプリの最初の画面が開くことを、外から確かめました
- 作る、使い方のタブを本番に入れました(2026-10-14)。本番と同じ写しを VM の別の口で立て、テストアカウントと本物の
  Gemini で、「今あるアプリを探す」が数分で終わり、結果から「課題を集める」に進めることを確かめました
- `flet build` でのアプリへの書き出しは、まだです
- `genba/` の記録の画面は、まだありません
