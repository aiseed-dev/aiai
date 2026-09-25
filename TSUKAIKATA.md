# 使い方の手引き

aiai の見本とスキルを、自分の書類や仕組みに使うまでの手順です。
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
   Web の画面を出す `flet-web` は conda-forge に無いので、pip で入れます

   ```
   conda install -c conda-forge fastapi uvicorn pyjwt cryptography flet
   pip install flet-web==1.0.1 --no-deps
   ```
4. AI を用意します。ファイルを読めて、コマンドを動かせる AI(AI のコーディング
   エージェントなど)が向いています。各フォルダーの `SKILL.md` を AI に読ませて使います

## 2. 自分の情報の扱い

- 自分の氏名、住所、電話、個人番号、生年月日を書いたファイルは、自分の機械の中だけに
  置きます。人に見せる前の材料は `材料.adoc` という名前にすると、`.gitignore` で
  リポジトリに入らないようになっています
- AI への依頼に、氏名、住所、電話、個人番号、生年月日を入れません。`tools/todoke.py` が
  書く依頼の文(`〜.依頼.md`)には、事業の内容だけが入ります
- 自分のデータを、公開のリポジトリに push しないでください

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

様式を埋めて PDF にするには、officework の次の版が要ります(いまの PyPI の 0.7.0 には
まだ入っていません)。書き方は [rirekisho/README.md](rirekisho/README.md) にあります。

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
なります。元に戻すときは `python office/install.py --remove` です。officework の次の版が
要ります。詳しくは [office/README.md](office/README.md) にあります。

## 9. 困ったとき、変わっていたとき

使って困ったこと、手続きをして分かったこと、書いてあることが変わっていたことは、
[報告のしかた](HOUKOKU.md)を見て知らせてください。報告は公開されるので、氏名や住所など、
人が分かることは書きません。

書いてある事実は、出典と確かめた日と一緒に書いています。制度や金額は変わるので、使う前に
確かめ直す物を一覧にできます。

```
python tools/kakunin.py --fetch --out 確認の結果.md
```

古い物、確かめた日の無い物、開けなくなった物、移った物が出ます。変わっていたら、
Issue の「新しい情報」で知らせてください。
