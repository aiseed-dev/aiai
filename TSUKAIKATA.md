# 使い方の手引き

aiai のスキルを、自分の書類や仕組みに使うまでの手順です。
コマンドは、このリポジトリのフォルダーで打ちます。

## 1. 用意する

1. このリポジトリを手元に取ります

   ```
   git clone https://github.com/aiseed-dev/aiai.git
   cd aiai
   ```

   git を使わないときは、GitHub の画面の「Code」から ZIP で取って開きます
2. Python 3 を入れます。`tools/` のスクリプトは、Python の標準ライブラリだけで動きます
3. 申し込みの仕組み(`moushikomi/`)を使うときは、部品を conda で入れます。
   Web の画面を出す `flet-web` は conda-forge に無いので、pip で入れます。`flet-web` と `flet` は同じ版にします

   ```
   conda install -c conda-forge fastapi uvicorn pyjwt cryptography flet=1.0.1 python-multipart websockets
   pip install flet-web==1.0.1 --no-deps
   ```
4. AI を用意します。各フォルダーの `SKILL.md` を AI に読ませて使います。ファイルを読めて、
   コマンドを動かせる AI(Claude のデスクトップアプリなど)だと、AI が手元で確かめられます。
   読むだけの AI でも、コマンドを自分で打てば使えます

## 2. 識別情報の扱い

氏名、住所、電話、生年月日、個人番号、メールアドレスのように、誰のことか分かる情報を、
この手引きでは識別情報と呼びます。

- 自分の識別情報を書いたファイルは、自分の機械の中だけに置きます。人に見せる前の材料は
  `材料.adoc` という名前にすると、`.gitignore` でリポジトリに入らないようになっています
- 自分の識別情報を AI に渡すかは、自分で決めます。渡した物が学習に
  使われるかは、使う AI のサービスの利用規約で確かめます。渡さなくても書類は作れます。
  `tools/todoke.py` が書く依頼の文(`〜.依頼.md`)には、事業の内容だけが入り、氏名や住所は
  コードが写します。個人番号だけは AI に渡しません(番号法第 20 条)
- 事業をするには、氏名、住所、電話を出す場面があります。開業届には書きますし、通信販売を
  するなら広告に事業者の氏名、住所、電話番号の表示が要ります(消費者庁「通信販売」、
  https://www.no-trouble.caa.go.jp/what/mailorder/ 、2026-09-28 に確かめました)。
  どこまで出すかは、自分で決めます
- 自分のデータ(識別情報と、事業の実際の値)を、公開のリポジトリに push しないでください。
  aiai のリポジトリに入れるのは、架空の見本だけです

### 公開のリポジトリに絶対に入れない物

識別情報より先に、次の物が入っていないかを見ます。1 度 push すると、消しても漏れた物として
扱う必要があります。

- API のトークンと鍵。AWS のアクセスキー、Google Cloud のサービスアカウントの JSON の鍵、
  Cloudflare の API トークン、Apple のサインインの鍵(`.p8`)、Anthropic や OpenAI の API キー
- パスワードが入った接続文字列。`postgresql://ユーザー:パスワード@ホスト/データベース` のような物
- `.env` のファイルと、compose や設定に直に書いたパスワードや秘密の値(`GOOGLE_CLIENT_SECRET`、
  `TURNSTILE_SECRET`、`JWT_SECRET` など)
- SSH の秘密鍵(`id_ed25519` など)と、TLS の秘密鍵(`.pem`、`.key`)
- お客さんの識別情報が入るデータベースのファイル(`moushikomi.db` など)

- 秘密の値は、環境の変数か、サーバーにだけ置く `.env` で渡します(`moushikomi/README.md` の
  設定の表がその形です)。`.gitignore` に `.env`、`*.p8`、`*.pem`、`*.db` が入っています
- コミットするときは、触ったファイルを名前で指定します(`git add .` を使いません)。
  何が入るかを毎回見ることになります
- GitHub の個人のアカウントには、対応している秘密の値を push の前に止める機能
  (push protection)が最初から有効です。止められる物は一部なので、頼り切りません
- 入ってしまったときは、まずそのトークンや鍵を無効にして作り直します。履歴から消す
  (`git filter-repo`)のは、その後です

出典: GitHub Docs「Push protection」
(https://docs.github.com/en/code-security/concepts/secret-security/push-protection)、
「Removing sensitive data from a repository」
(https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。
2026-09-28 に確かめました。

## 3. 開業届と青色申告承認申請書([kaigyo](kaigyo/))

1. 見本を動かします

   ```
   python tools/todoke.py tsukuru kaigyo/事業.sheet.adoc kaigyo/開業届.koumoku.adoc
   ```

   `kaigyo/開業届.sheet.adoc` と、AI への依頼の文 `kaigyo/開業届.依頼.md` ができます。
   画面に、この届のために本人が書く項目が出ます
2. 自分の分を作るときは、`kaigyo/事業.sheet.adoc` を写して、自分の事業のことを書きます
3. `〜.依頼.md` を AI に渡し、残った項目を AI と一緒に考えて埋めます。決めるのは本人です
4. 受け取る側は、届いた adoc をまとめて確かめます

   ```
   python tools/todoke.py uketsuke kaigyo/開業届.koumoku.adoc kaigyo/見本
   ```

   直す所と、全員の値を 1 つの表にした `受付一覧-開業届.adoc` ができます

## 4. 農業を始める([nougyou](nougyou/))

1. [nougyou/README.md](nougyou/README.md) で、手続きの一覧と出典を見ます
2. 自然農法の経営計画は、AI に [nougyou/keikaku/SKILL.md](nougyou/keikaku/SKILL.md) を
   読ませて作ります。最初に、自然農法系の農業のいいことと難しいことを読みます。
   収量、単価、経費、労働時間の数字は、本人が根拠と一緒に決めます
3. 計算します

   ```
   python nougyou/keikaku/keikaku.py nougyou/keikaku/経営計画.sheet.adoc
   ```

   年ごとの売上、経費、農業所得、労働時間と、青年等就農計画に写す値が出ます
4. 青年等就農計画のデータを作ります

   ```
   python tools/todoke.py tsukuru nougyou/事業.sheet.adoc nougyou/青年等就農計画.koumoku.adoc
   ```

## 5. 履歴書([rirekisho](rirekisho/))

どういう内容を書くかは、本人と、本人が使っている AI に任せます。書く内容の見本や手本は、
その AI が作れます。aiai が扱うのは、様式と、
決まりとして知られていること(記入上の注意など)だけです。

様式を埋めて PDF にするには、officework の様式を埋める機能が要ります。この機能は、いま PyPI に
ある officework 0.7.0 には、まだ入っていません。書き方は [rirekisho/README.md](rirekisho/README.md) にあります。

## 6. Web サイト([website](website/))

1. AI に [website/SKILL.md](website/SKILL.md) を読ませます。AI が、誰に来てほしいか、
   その人が最初に知りたいことは何かを聞きながら、ページを一緒に書きます
2. 見本を作ってみます

   ```
   python tools/todoke.py tsukuru kaigyo/事業.sheet.adoc website/Webサイト.koumoku.adoc
   python website/sample/build.py website/sample --out _site
   ```

   `_site/index.html` をブラウザーで開きます
3. 公開は、Cloudflare Pages でします。手順は [website/SKILL.md](website/SKILL.md) の 7 にあります。
   名前の要らないお問い合わせは、Cloudflare の Workers と R2 で受けられます(同じく 8)

## 7. 申し込み(取り置き、予約、注文)([moushikomi](moushikomi/))

名前が要る申し込みは、先に Apple ID か Google ID でサインインしてもらい、本人の
サーバーで受けます。預かる物には本人が責任を持つので、要る物だけを預かります。

1. AI に [moushikomi/SKILL.md](moushikomi/SKILL.md) を読ませ、預かる項目を一緒に考えます。
   見本は、パンの取り置き(`moushikomi/取り置き.koumoku.adoc`)です
2. 確かめます

   ```
   python moushikomi/test_server.py
   ```

3. 画面を手元で試します。偽の Apple と Google を使うので、アカウントは要りません

   ```
   python moushikomi/fake_id.py moushikomi/取り置き.koumoku.adoc
   ```

   `http://127.0.0.1:8000/app/` を開き、サインインの画面で架空の人を選びます
4. 本当に使うときは、本人が Apple Developer Program と Google Cloud Console で
   サインインの準備をし、本人のサーバーで `server.py` を動かします。設定は
   [moushikomi/README.md](moushikomi/README.md) にあります

## 8. 書類を直す(office)

officework のリボンを、書類を書いて直すための形にします。

```
python office/install.py
```

タブは、ファイル、書類、ホーム、挿入、レイアウト、共同編集、表示、確かめる、報告 に
なります。元に戻すときは `python office/install.py --remove` です。この設定を読む機能は、
いま PyPI にある officework 0.7.0 には、まだ入っていません。詳しくは [office/README.md](office/README.md) にあります。

## 9. 困ったとき、変わっていたとき

使って困ったこと、手続きをして分かったこと、書いてあることが変わっていたことは、
[報告のしかた](HOUKOKU.md)を見て知らせてください。報告は公開されるので、識別情報は書きません。

書いてある事実は、出典と確かめた日と一緒に書いています。制度や金額は変わるので、使う前に
確かめ直す物を一覧にできます。

```
python tools/kakunin.py --fetch --out 確認の結果.md
```

古い物、確かめた日の無い物、開けなくなった物、移った物が出ます。変わっていたら、
Issue の「新しい情報」で知らせてください。
