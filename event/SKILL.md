---
name: event
description: PHP や WordPress で動いている Web サイトを、静的なサイトと Flet の問い合わせのフォームに作り直し、Cloudflare に無料で公開する。問い合わせは Worker で確かめて R2 に置き、担当者が Flet のアプリで受け取る。本人は HTML も JavaScript も知らなくてよい
---

# 静的サイトと Flet のフォームへの作り直し

PHP や WordPress で動いているサイトを、PHP を使わない形に作り直します。コードはあなた(AI)が書きます。本人は動きを確かめ、
直したい所をあなたに伝えます。本人は HTML も JavaScript も知らない前提で進めます。

考え方: 動く部分を減らせば、守る部分も減ります。サイトは静的なファイルだけにし、PHP もデータベースも置きません。問い合わせの
フォームは誰でも送れる口なので、来た物は全部疑い、量を絞ります。

## やること

目標 1 は静的なサイトの公開(1〜3 の段)、目標 2 は問い合わせのフォームの作成(4〜7 の段)です。目標 1 ができたら、そう本人に伝えます。

段ごとに、何を作るかを先に 2〜3 行で伝え、作り、本人に確かめてもらってから次に進みます。コマンドは 1 つずつ示し、何が起きるかを
1 行添えます。本人が見た物(画面、エラーの文)を伝えてきたら、それを元に直します。

1. 載せる中身を `content/` の Markdown にします
   - 今のサイトがある場合: 棚卸しはしません。トップページの中身(文章、画像、リンク)を `content/index.md` に、トップページから
     リンクしているお知らせがあれば、一覧(「次へ」で続くページも)と一つ一つのお知らせを一連で `content/oshirase/` に 1 件 1 ファイルで
     書き、件数を伝えます。今のサイトに書いていない事実は足しません
   - 新しく作る場合: 本人に聞かずに、本人が書いた中身で、すぐに `content/` を書き、2 の段まで続けます。本人が空欄にした所だけを
     「(ここに〇〇を書く)」の形で空け、書いていない事実も項目も足しません
2. `build.py` を作り、手元で見えるようにします。仮想環境に `markdown` を入れ、`python build.py` で `public/` を作り、
   `python -m http.server 8000 -d public` で `http://localhost:8000/` を開いてもらいます。チャットのときは、ファイルを本人に保存して
   もらいます
3. Cloudflare Pages に上げます。本人がアカウントの ID と API トークンを用意したら、同じ仮想環境に cf-publish を入れ、トークンを書く
   ファイルの置き場所と書き方を伝えます。上げるコマンドは、プロジェクトの名前の案(例: `kakuu-koumuten`)を入れて出します
- デザインを考える(目標 1 の後、頼まれたら): 業種に合う案を 3 つ(いちばん目立たせる物、色、字体)出し、本人が選んでから `build.py` の
  ページの形を作り直し、手元で見てから上げ直します
4. 受け口の Worker と R2 のバケットを上げます。1 分と 1 日に受ける数は、案と、選ぶと何が変わるかを出して、本人と決めます
5. 問い合わせのフォームを Flet で作り、`flet build web` で書き出して、`public/toiawase/` の「準備中」と入れ替え、上げ直します
6. 担当者のアプリと、短い利用者マニュアル(`uketori/manual.md`)を作ります。保存先は、案を出して本人と決めます
7. 本人がフォームから 1 件送り、担当者のアプリで受け取り、R2 から消えたことを確かめます

## 決まっていること

### 置き場所

作業のフォルダー 1 つの中に置きます。Python の部品(`markdown`、`cf-publish`、`flet`)は、その中の仮想環境に入れます。

- `content/`: 中身(Markdown)。`index.md` がトップページ、`oshirase/<日付>-<短い名前>.md` がお知らせ 1 件
- `build.py`: `content/` から `public/` に HTML を作る
- `public/`: Pages に上げる物。フォームは `public/toiawase/`
- `toiawase/`: フォームの Flet のアプリ(`main.py`)
- `worker/`: 受け口(`worker.js`、`wrangler.toml`)
- `uketori/`: 担当者のアプリ(`main.py`)と利用者マニュアル(`manual.md`)

### 静的なサイト

WordPress と同じように、中身とページの形を分けます。お知らせを足すときは、Markdown を 1 つ足して `build.py` を動かし、上げ直します。

- お知らせの Markdown の先頭に、題と日付を書きます

  ```
  ---
  title: 年末年始の休み
  date: 2026-10-20
  ---
  本文
  ```

- `build.py` が作るページ: `public/index.html`(トップページ。新しいお知らせを数件並べる)、`public/oshirase/index.html`(一覧、新しい順)、
  `public/oshirase/<短い名前>.html`(1 件ずつ)。トップページから一覧へ、一覧から 1 件ずつへリンクします。リンクは `.html` まで書きます
  (手元の `http.server` は `.html` が無いと開けません。Pages は `.html` を外した URL に 308 で移しますが、そのまま開けます)
- Markdown は `markdown`(Python-Markdown)で HTML にします。ページの形と CSS は `build.py` の中に書き、ファイルを増やしません
- HTML と CSS だけを出し、JavaScript は使いません。今のサイトの文章と画像だけを使い、PHP のファイルは持ってきません
- フォームへのリンク(`/toiawase/`)を置きます。`public/toiawase/index.html` が無いときだけ「準備中」のページを作り、あるときは触りません
- パソコンの幅でもスマートフォンの幅でも崩れないようにします
- デザインは業種に合わせます。その業種で使う物(看板、帳面、品書きなど)から形を 1 つ取っていちばん目立つ所に使い、ほかは飾りません。
  字体は PC に入っている物だけを使い、色は 3〜4 色にします。営業日や料金のように並びのある中身は、表や印のように見て分かる形にします
- 見本で作るときは、架空の会社にし、架空と書きます
- チャットのときは、保存した名前の最後が `.md`、`.py` になっているかを本人に確かめてもらいます(Windows では `.txt` が付くことがあります)

### 問い合わせのフォーム

- 上から、見出し「お問い合わせ」、「お名前」(50 文字まで)、「メールアドレス」(254 文字まで)、「お問い合わせの内容」(数行、
  2000 文字まで)、送った内容は Cloudflare に置き担当者が受け取ったら消すという説明、ボタン「送る」、結果
- 送っている間はボタンを押せなくし、受け付けたら入力を消して「受け付けました」と出します。断られたら、Worker が返した理由をそのまま出します
- 送り先の Worker の URL は、`main.py` の先頭の定数 `WORKER_URL` に書きます
- 書き出した物はブラウザーの中の Python(Pyodide)で動くので、送るのは `pyodide.http.pyfetch` です。`urllib` と `requests` は使いません
- 書き出しは `toiawase/` の中で `flet build web --base-url toiawase`。`toiawase/build/web` の中身を `public/toiawase/` に写します。
  初めてのときは Flutter SDK を自動で入れるので、時間がかかります
- R2 に支払いの方法を登録したくない人は、Google フォームへのリンクでもかまいません(4〜6 の段は要りません)

### 受け口の Worker

口は 4 つだけです。

| 口 | 誰が | すること |
|---|---|---|
| `POST /toiawase`(と `OPTIONS`) | フォーム | 確かめて、通れば R2 に 1 件置く |
| `GET /uketori` | 担当者のアプリ | `toiawase/` の下の一覧(`kazu/` の印は返さない) |
| `GET /uketori/<名前>` | 担当者のアプリ | 1 件を読む |
| `DELETE /uketori/<名前>` | 担当者のアプリ | 1 件を消す |

`POST /toiawase` は、次をすべて確かめ、1 つでも通らなければ置きません。理由は、フォームにそのまま出せる日本語で返します。

- 送り元(`Origin`)が `SITE_ORIGIN` と同じ。`Origin` が無い物も受け取らない
- JSON で、本文が 10,000 文字まで。項目は `namae`、`mail`、`naiyou` の 3 つだけで、どれも文字。改行とタブのほかの制御文字は捨てる
- お名前と内容が空でなく、メールアドレスの形をしている。内容の中のリンクは 2 つまで
- 同じ 1 分(日本時間)に受けた数が `MAX_PER_MINUTE`(既定 5)より少ない(ボットがまとめて送る物を止める)。その日に受けた数が
  `MAX_PER_DAY`(既定 500)より少ない(ふだんは届かない外側の守り)
- 数えるのは `kazu/<日付>/<時分>/` に置いた印の数。受け付けるたびに中身の無い印を 1 つ置き、担当者のアプリでは消しません
  (問い合わせの方を数えると、受け取るたびに枠が空くため)

送り元が合っていれば、断る返事(400、413、415、429)にも `Access-Control-Allow-Origin` を付けます。付けないと、フォームに理由が出ません。

置くのは、書かれた 3 項目と受け付けた時刻だけです。IP アドレスとブラウザーの種類は置きません。名前は `toiawase/<日付>/<時刻>-<乱数>.json` です。

担当者の口は、`Authorization: Bearer <STAFF_TOKEN>` が合うときだけ答えます。`STAFF_TOKEN` が無いときも閉じます。比べ方は、かかる時間が
中身で変わらない比べ方にします。`<名前>` は、上の形に合う物だけを受けます。

`wrangler.toml` には `name`、`main`、`compatibility_date`、R2 のバインディング(`TOIAWASE`、バケット `toiawase`)、`[vars]` の
`SITE_ORIGIN`、`MAX_PER_MINUTE`、`MAX_PER_DAY` を書きます。npm の部品は使いません。

上げる前に、R2 を手元の偽物にした試験を書いて、上の確かめを 1 つずつ試します。Node.js があれば `node` で動かします。

上限は量を絞るだけです。多数の送り元から集中して送られたら、受け口を止めます(`cf-publish worker deploy worker --no-workers-dev` で
URL を閉じ、サイトからフォームへのリンクを外して上げ直す)。最後の守りは認証(Apple ID と Google ID)ですが、この手引きでは作りません。

### 担当者のアプリ

- Flet のデスクトップのアプリ。`flet run uketori/main.py` で動かします
- 送り先と鍵は `~/.config/toiawase.env` の `TOIAWASE_URL` と `TOIAWASE_TOKEN` から読みます。画面に入れる欄は置きません
- 「受け取る」で 1 件ずつ読み、保存先(案は `~/toiawase/`)に JSON で保存し、保存できた物だけを R2 から消します
- 保存した物を新しい順に、受け付けた時刻(日本時間に直す)、お名前、メールアドレス、内容で見せます
- Worker を呼ぶときはアプリの名前を `User-Agent` に付けます(例: `toiawase-uketori/1.0`)。Python の `urllib` の既定の名前は、
  Cloudflare に「error code: 1010」(403)で断られます
- 利用者マニュアルは、担当者がすることだけを短く: 起動の仕方、「受け取る」、保存先と中身の見方、受け取った物は Cloudflare から
  消えていること、受け取れないときに見る所(鍵のファイル、ネットのつながり)

### 公開(cf-publish)

cf-publish(https://github.com/aiseed-dev/cf-publish)で上げます。wrangler と Node.js は使いません。

| 上げる物 | コマンド |
|---|---|
| 静的なサイトとフォーム | `cf-publish public --project <プロジェクト名>` |
| Worker と R2 のバケット | `cf-publish worker deploy worker --secret STAFF_TOKEN --workers-dev` |

- トークンの権限は、目標 1 は「Cloudflare Pages: 編集」だけ。目標 2 の前に「Workers Scripts: 編集」と「Workers R2 Storage: 編集」を
  足してもらいます。トークンとアカウントの ID は、本人が `~/.config/cloudflare/pages.env` に `CLOUDFLARE_API_TOKEN=` と
  `CLOUDFLARE_ACCOUNT_ID=` の形で書きます
- `STAFF_TOKEN` は、本人が `python -c "import secrets; print(secrets.token_urlsafe(32))"` で作り、`~/.config/toiawase.env` と、
  上げるときの環境の変数にだけ置きます
- R2 のバケットは無ければ `worker deploy` が作ります。その前に、本人が R2 を使い始める手続き(支払いの方法の登録)を済ませておく
  必要があります
- Pages の URL は `https://<プロジェクト名>.pages.dev` です。cf-publish が出す 8 桁入りの URL はその回だけの物で、`SITE_ORIGIN` には
  使いません
- Worker の URL は `--workers-dev` を付けると出ます。サブドメインが無いと言われたら、「Workers & Pages」の「Your subdomain」を見てもらいます
- 順番: Pages を上げる → `SITE_ORIGIN` に書く → Worker を上げる → `WORKER_URL` に書いて書き出す → Pages を上げ直す

### 秘密の値

API トークン、アカウントの ID、`STAFF_TOKEN` は、本人がファイルに書きます。チャットに貼ってもらわず、コードにも書きません。貼られたら、
無効にして作り直すよう伝えます。

## 確かめ方

- 静的なサイト: 手元と Pages の URL で、ページとリンクがすべて開くか(フォームは 5 の段まで「準備中」)。パソコンとスマートフォンの
  幅で崩れないか。お知らせの Markdown を 1 つ足して `build.py` を動かすと、トップページと一覧に出るか
- Worker: 偽物の R2 での試験がすべて通るか
- フォーム: 送って「受け付けました」が出るか。空のお名前、形の違うメールアドレス、リンク 3 つは、理由が出て断られるか
- 担当者のアプリ: 利用者マニュアルのとおりに使えるか。受け取って保存され、もう一度押しても増えないか
- 古いサイト: PHP と管理画面を公開したままにしていないか。古い URL から新しい URL への移し(Pages の `_redirects`)が要るか
