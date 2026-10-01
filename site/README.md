# aiai のサイトとアプリ

| ファイル | 中身 |
|---|---|
| `index.html`、`top.css` | トップページ。手で書いた HTML と CSS だけで、外の書体や部品は読み込みません |
| `app/main.py` | Flet の画面。スキルの一覧(開いて「写す」で写し、自分の AI に貼る)、考え方、お知らせ、相談の 4 つのタブ。同じコードを `flet build` で iPhone と Android のアプリにする予定です |
| `app/soudan_view.py` | 相談のタブ。`soudan/server.py` と話します |
| `app/assets/` | アプリが持ち歩く物。`kangaekata.md`(考え方)、`news/*.adoc`(お知らせ)、`skills/`(各フォルダーの `SKILL.md` の写し。`make_assets.py` が作り、リポジトリには入れません) |
| `make_assets.py` | 各フォルダーの `SKILL.md` を `app/assets/skills/` に写します。標準ライブラリだけ |
| `server.py` | `/` でトップページ、`/app/` で Flet の画面、`SOUDAN_MODELS` があれば `/soudan/` でセカンドオピニオンのサーバーを出します |
| `try.py` | 偽の Apple と Google と、偽のモデル 2 つで、全部を手元で立てます。試すためだけの物です |

## 動かす

部品は `moushikomi/` と同じです(conda-forge の `fastapi`、`uvicorn`、`pyjwt`、`cryptography`、
`python-multipart`、`websockets`、`flet`、pip の `flet-web`)。

```
python site/make_assets.py
python site/try.py
```

`http://127.0.0.1:8020/` を開きます。相談のタブでは、偽の Apple か Google でサインインし、
`try.py` が表示する試しの招待の番号を入れます。

本物で動かすときは、`soudan/README.md` の設定(`BASE_URL` は `/soudan` で終わる物)と、
`app/soudan_view.py` の `AIAI_SOUDAN`、`AIAI_SOUDAN_API`、`AIAI_RETURN` を環境の変数で渡して、
`python site/server.py` を動かします。

## いまの状態

- deb2 の dev のホームで動かし、ブラウザーで押して確かめました(2026-10-02)。トップページ、
  3 つのタブ、「写す」、相談のタブのサインインから評価と出来事まで
- aiai.aiseed.dev での公開と、`flet build` でのアプリへの書き出しは、まだです
- `genba/` の記録の画面は、まだありません
