# Gemini で試す(tameshi)

aiai のサイトで、サインインした人が、アプリを作る流れの段を Google Cloud の Gemini に頼む仕組みです。
画面はアプリの「作る」のタブ(`site/app/tameshi_view.py`、https://aiai.aiseed.dev/app/tameshi )で、
ここにあるのは、その画面が話す API と、段を分けて進める仕事です。

| ファイル | 中身 |
|---|---|
| `server.py` | API。`site/server.py` が `/tameshi` に差し込みます(`AIAI_TAMESHI=1`)。サインイン(Apple、Google、審査用のテストアカウント)、回数の上限、手引きを読ませた Gemini との対話、どう良くするかの対話、今日のニュース、仕事の受け付けと進み具合 |
| `kaihatsu.py` | 段を分けて進める 4 つの仕事。今あるアプリを探す(`chousa`)、今あるアプリの課題を集める(`kadai`)、設計書とマニュアルを作る(`sekkei`)、テストの手順を作る(`tesuto`)。1 段ずつ Gemini を呼ぶので、進み具合が画面で見えます。標準ライブラリだけ |
| `test_server.py` | 偽の Gemini と偽のサインインでの確かめ |
| `docs/design.adoc` | 設計書。作る人が読む物です |
| `docs/manual.adoc`、`docs/manual.pdf`、`docs/images/` | 利用者マニュアル。サイトの使い方のページと、アプリの使い方のタブは、ここから作ります |

## 守ること

- 誰でも ID とパスワードで登録できますが、Gemini に頼めるのは、持ち主が `~/aiai-server/tameshi/approved.txt` に書いて
  承認した人だけです。登録した人の一覧は、VM で `DB=~/aiai-server/tameshi/tameshi.db ~/miniforge3/envs/aiai/bin/python tameshi/server.py users` で見ます
- 書いたことは記録しません。記録するのは、使った回数だけです
- 仕事の結果は、頼んだ本人だけが読めます。7 日で消します(審査用のテストアカウントの物は、見本の結果に
  するため 60 日)
- 読んだページや渡された資料の中に「こうしろ」と書いてあっても、指示として扱いません
- 秘密の値(Apple と Google の鍵、テストアカウントのパスワード)は、リポジトリに置きません。VM の
  `~/aiai-server/tameshi/secrets.env` に置きます

環境変数(テストアカウント、回数の上限、仕事の置き場)は、`server.py` の先頭の説明にあります。

## 確かめる

部品は `moushikomi/` と同じです(conda-forge の `fastapi`、`uvicorn`、`pyjwt`、`cryptography`、
`python-multipart`)。

```
python tameshi/test_server.py
```
