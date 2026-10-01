# 申し込み

Apple ID か Google ID でサインインした人から、申し込み(パンの取り置き、教室の予約、
注文など)を受けるスキルです。静的な Web サイトではできない物の多くは、同じ形になります。

1. 名前が要るので、先にサインインしてもらう
2. 申し込みに要る物だけを預かる
3. 本人が自分の申し込みを見て、取り消す
4. 期限が過ぎたら消す

違うのは、預かる項目だけです。項目は `.koumoku.adoc` に書きます。書き方は、開業届などの
項目と同じです。見本は、架空のパン屋「はなこパン」の取り置き(`取り置き.koumoku.adoc`)です。

AI に [SKILL.md](SKILL.md) を読ませると、AI が本人に聞きながら、預かる項目を一緒に考えます。

## 仕組み

- `server.py` は、本人のサーバーで動かします。店や自宅の機械でも、借りるサーバーでも、
  同じように動きます。Apple と Google とのやり取り、申し込みの保存は、すべてここでします。
  Apple の秘密鍵や Google のクライアントシークレットは、このサーバーの外に出ません
- 画面(`app/main.py`)は Flet で作ります。`server.py` が、API と同じアドレスの `/app/` で
  Web の画面として出します。同じコードを、iPhone と Android のアプリにも書き出す予定です
- 画面は、サインインの入口(`/login/apple`、`/login/google`)に人を送ります。サインインの後、
  サーバーは 1 回だけ使える引き換えの番号(1 分で切れます)を付けて画面に戻し、画面はそれを
  `POST /api/session` で札(トークン)と引き換えて、申し込みの API を呼びます。札そのものは
  アドレスに出ません
- 預かるのは、Apple や Google が渡す人ごとの番号(sub)、Apple や Google が確かめたメール
  アドレス、項目に書いた物だけです。名前は Apple にも Google にも求めません
- 期限の日(`:期限:` に書いた項目)が過ぎた申し込みは、消えます。サインインの札は
  30 日で切れ、データベースには札そのものではなく、ハッシュを置きます

| API | 中身 |
|---|---|
| `GET /login/{apple か google}?next=戻り先` | サインインを始めます。戻り先は、設定の `RETURN_URLS` にある物だけです |
| `POST /api/session` | 引き換えの番号を札に替えます |
| `GET /api/form` | 項目の一覧と決まり |
| `GET /api/me` | サインインしている人(メールアドレスと、店の人かどうか) |
| `GET`、`POST /api/requests` | 自分の申し込みの一覧と、新しい申し込み |
| `DELETE /api/requests/{id}` | 自分の申し込みの取り消し |
| `GET /api/shop/requests` | 店の人だけが見る、すべての申し込み |
| `POST /api/logout` | サインアウト |

## ファイル

| ファイル | 中身 |
|---|---|
| `SKILL.md` | AI への手順。預かる項目を本人と考える |
| `取り置き.koumoku.adoc` | 見本の項目(架空のパン屋の取り置き) |
| `server.py` | 申し込みのサーバー(サインイン、API、期限で消すこと、画面を出すこと) |
| `app/main.py` | 画面(Flet)。項目の一覧から欄を作るので、項目を変えても直さなくてよい |
| `fake_id.py` | 手元で試すための偽の Apple と Google |
| `test_server.py` | サインインから取り消しまでの確かめ |

## 項目の書き方

`取り置き.koumoku.adoc` を見本にします。項目の表と、品物のように行が増える物の表
(`.表`、`.表の列`)は、`tools/todoke.py` の決まりのままです。そのほかに、次の属性を書きます。

| 属性 | 中身 |
|---|---|
| `:期限:` | この日が過ぎたら申し込みを消す、日付の項目の名前 |
| `:何日先から:`、`:何日先まで:` | 期限の日として選べる範囲(今日から何日先) |
| `:休みの曜日:` | 期限の日にできない曜日(`日・月` のように書きます) |
| `:一人あたりの件数:` | 一人が同時に持てる申し込みの数 |
| `:一つの品物の数まで:` | 表の「数」の列の上限 |

## 動かす

Python の部品は、conda で入れます(conda-forge の `fastapi`、`uvicorn`、`pyjwt`、
`cryptography`、`flet`、`python-multipart`、`websockets`)。Web の画面を出す `flet-web` は
conda-forge に無いので、pip で入れます(`pip install flet-web==1.0.1 --no-deps`)。`flet` は
`flet-web` と同じ版(1.0.1)にします。

```
conda install -c conda-forge fastapi uvicorn pyjwt cryptography flet=1.0.1 python-multipart websockets
pip install flet-web==1.0.1 --no-deps
```

`python-multipart` は、Apple から POST で届くサインインの結果を受け取るのに要ります。
`websockets` は、Web の画面がサーバーとつながるのに要ります。pip で fastapi と uvicorn を
入れたときは、この 2 つが入らず、サーバーが止まるか、画面が「Working...」のまま進みませんでした。

```
python moushikomi/test_server.py
```

偽の Apple と Google を手元で立て、サインインから取り消しまでを通して確かめます。

```
python moushikomi/fake_id.py moushikomi/取り置き.koumoku.adoc
```

サーバーと画面を、偽の Apple と Google と一緒に手元で立てます。`http://127.0.0.1:8000/app/` を
開き、サインインの画面で架空の人を選びます。店の人として試すときは `owner@example.jp` を
選びます。`fake_id.py` は試すためだけの物で、本物のサーバーでは使いません。

```
python moushikomi/server.py moushikomi/取り置き.koumoku.adoc --port 8000
```

画面を出さず API だけにするときは、`--no-screen` を付けます。

設定は、環境の変数で渡します。秘密の値をリポジトリに入れないためです。

| 変数 | 中身 |
|---|---|
| `BASE_URL` | このサーバーの外からのアドレス(例: `https://yoyaku.example.jp`) |
| `RETURN_URLS` | サインインの後に戻してよい先(空白で区切ります)。Web サイトとアプリのリンク |
| `DB` | データベースのファイル(既定は項目のファイルの隣の `moushikomi.db`) |
| `SHOP_EMAILS` | 店の人のサインインのメールアドレス(空白で区切ります) |
| `TIMEZONE` | 既定は `Asia/Tokyo` |
| `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET` | Google Cloud Console で作るクライアント |
| `APPLE_SERVICES_ID`、`APPLE_TEAM_ID`、`APPLE_KEY_ID`、`APPLE_KEY_FILE` | Apple Developer で作る Services ID と、Sign in with Apple の鍵(.p8) |

`moushikomi.db` にはお客さんのメールアドレスが入り、`.p8` はサインインの鍵です。
どちらも `.gitignore` でリポジトリから外してあります。

## Apple と Google の違い

どちらも OpenID Connect です。接続先は、それぞれの公開の設定(discovery)から読みます。
Apple は、次の 3 つが Google と違い、`server.py` がそれぞれに合わせています。

- クライアントシークレットは、Apple の鍵(.p8)で本人のサーバーが署名する JWT(ES256)です。
  Apple の決まりでは有効期限は 6 か月までで、`server.py` は、やり取りのたびに 5 分の物を作ります
- サインインの結果は、Apple のサイトから本人のサーバーへの POST(form_post)で届きます。
  そのため、サインインの途中の値(state、nonce)は、クッキーではなくサーバーに置きます
- 名前は、最初のサインインのときにしか渡されません。この仕組みは名前を求めず、店で呼ぶ
  呼び名を申し込みの項目で聞きます

## 確かめたこと

- `test_server.py` で、17 の確かめが通りました(Python 3.14、macOS)。Debian 13 でも、
  conda の Python 3.14.7 と、venv の Python 3.13.5 で、17 の確かめが通りました(2026-10-01)。
  サインイン(Apple、Google)、Apple のクライアントシークレットの署名、戻り先の制限、
  state を 1 回しか使えないこと、id_token の署名・発行元・宛先・期限・nonce の確かめ、
  確かめていないメールアドレスを預からないこと、項目の決まり、一人あたりの件数、
  他人の申し込みを見られず消せないこと、店の人の一覧、期限が過ぎたら消えること、
  サインアウト、札をハッシュで置くこと、引き換えの番号を 1 回しか使えないこと、
  偽のサインインの画面
- `server.py` から、id_token の署名、発行元、宛先、期限、nonce の確かめ、state を消す所、
  戻り先の制限、本人だけが取り消せる所、休みの曜日、メールアドレスの確かめを、1 つずつ
  外して試し、どれもテストが失敗することを確かめました
- 本物の Apple と Google では、まだ試していません。店の Apple Developer の登録と、
  Google Cloud Console のクライアントができてから試します
- `fake_id.py` で立て、Web の画面をブラウザーで開いて、次のことを実際に押して確かめました。
  偽の Apple と Google でのサインイン、呼び名・取りに来る日・パンの数を選んでの申し込み、
  足りないときの知らせ、自分の申し込みの一覧、店の人の一覧、サインアウト、取り消し。
  取りに来る日には、明日から 7 日先までのうち、休みの日曜と月曜を除いた日だけが出ました。
  スマートフォンの幅(375 ピクセル)でも横にはみ出しませんでした(Flet 1.0.1)
- Flet の Dropdown は、選んだ値が Python の側に届かないことがあったので、`on_select` で
  受け取った値を使っています
- iPhone と Android のアプリへの書き出し(`flet build`)は、まだ試していません

出典: Google「OpenID Connect」(https://developers.google.com/identity/openid-connect/openid-connect)、
Google の discovery(https://accounts.google.com/.well-known/openid-configuration)、
Apple の discovery(https://appleid.apple.com/.well-known/openid-configuration)、
Apple「Creating a client secret」
(https://developer.apple.com/documentation/accountorganizationaldatasharing/creating-a-client-secret)、
Apple「Configure Sign in with Apple for the web」
(https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web/)。
2026-09-25 に確かめました。
