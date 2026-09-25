# aiai

履歴書、開業の届出、就農の計画、事業の Web サイト、お客さんからの申し込みのように、
決まった形の書類や仕組みを、AI と一緒に自分で作るための見本とスキルです。

使い方は、[使い方の手引き](TSUKAIKATA.md)にまとめています。

## 使う人と一緒に育つ

このリポジトリは、使う人と一緒に育っていきます。

- 実際に手続きをした人の報告で、様式、手順、スキルを直します
- 制度や金額は変わります。書いてある事実には出典と確かめた日を付け、`tools/kakunin.py` で
  確かめ直す物を一覧にします。変わっていたら、「新しい情報」として知らせてもらい、直します
- 報告のしかたは [HOUKOKU.md](HOUKOKU.md) にあります

## 考え方

### 誰が何をするか

書類を作る仕事を、次のように分けます。

| 何を | 誰が |
|---|---|
| どの書類でも同じ内容(氏名、住所、屋号など)を写す | コード |
| 書類の目的に合わせて文を書く(事業の概要など) | AI が本人の言葉から下書きし、本人が直す |
| 本人にしか決められないこと(青色申告にするか、など) | 本人 |

### AI は、本人が考えることを助ける

- 答えを先に出しません。何のための項目か、選ぶと何が変わるかを伝え、本人に 1 つずつ聞きます
- 文は、本人が書いた言葉から下書きします。本人が言っていないことは足しません
- AI に渡すのは事業の内容だけです。氏名、住所、電話、個人番号、生年月日は渡しません

各フォルダーの `SKILL.md` は、AI に読ませる手順です。

### 書類のファイルの形

書類のデータは、adoc という文字のファイルで書きます。テキストエディターで開けて、
GitHub の画面では表になります。表計算やワープロのソフトは要りません。

## 中身

| フォルダー | 中身 |
|---|---|
| [kaigyo](kaigyo/) | 開業届と青色申告承認申請書の項目、見本のデータ、受け取る側の見本 |
| [nougyou](nougyou/) | 農業を始めるときの手続き(出典と確かめた日付き)、青年等就農計画の項目と見本のデータ |
| [nougyou/keikaku](nougyou/keikaku/) | 自然農法の経営計画を作るスキル。自然農法系の農業の紹介(いいことと難しいこと)と、年ごとの計算 |
| [rirekisho](rirekisho/) | 履歴書の様式(厚生労働省の様式例、JIS 様式)と見本のデータ |
| [website](website/) | 事業の Web サイトを作るスキル。開業届と同じデータから公開してよい事実だけを写し、Cloudflare Pages で公開する。名前の要らないお問い合わせは Cloudflare の Workers と R2 で受ける |
| [moushikomi](moushikomi/) | Apple ID か Google ID でサインインした人から、申し込み(取り置き、予約、注文など)を受ける仕組み。預かる項目を adoc に書き、画面は Flet で作る |
| [office](office/) | officework の簡易版。書類を書いて直すための、リボンの設定ファイルと Python のボタンだけを置く |
| [tools](tools/) | `todoke.py`(書類ごとのデータを作る、受け取って確かめる)、`houkoku.py`(報告の下書き)、`kakunin.py`(出典を確かめ直す物を出す)、`office_kit.py`(office のボタンが使う) |

見本の人、店、数字は、すべて架空です。

## 使う物

| 使う所 | 要る物 |
|---|---|
| `tools/todoke.py`、`nougyou/keikaku/keikaku.py`、`website/sample/build.py` | Python 3 だけ(Python 3.9 で確かめました) |
| `moushikomi/` | Python 3 と、conda-forge の `fastapi`、`uvicorn`、`pyjwt`、`cryptography`、`flet`。Web の画面には pip の `flet-web`(Python 3.14 で確かめました) |
| `website/` の公開とお問い合わせ | Cloudflare のアカウント(無料のプランで使えます) |
| 様式を埋めて PDF にする、履歴書、`tools/houkoku.py`、`office/` | [officework](https://github.com/aiseed-dev/officework)。印とデータの書き方は、officework の [様式の手引き](https://github.com/aiseed-dev/officework/blob/main/docs/ja/forms-manual.adoc)にあります |

officework は、aiai とは別のプロジェクトです。aiai は公開されている版を使うだけで、
機能が足りないときやバグは、officework の Issues に報告します。aiai が使う機能(様式を埋める
`Book.fill` と、リボンの設定ファイル)は、いま PyPI にある officework 0.7.0 には、まだ入っていません。

## いまの状態

- 動かして確かめた物: `tools/todoke.py`、`nougyou/keikaku/keikaku.py`、`website/sample/build.py`、
  `moushikomi/`(偽の Apple と Google を相手にしたテストと、Web の画面を押して確かめること)
- まだ確かめていない物:
  - Cloudflare Pages での公開と、お問い合わせの関数
  - `moushikomi/` を本物の Apple と Google で使うこと。iPhone と Android のアプリへの書き出し
  - `office/` の Linux と Windows での動き
- 自然農法の経営計画は、福岡正信の著作からの引用を、これから足します

## 報告

使って困ったこと、実際に手続きをして分かったこと、書いてあることが変わっていたことは、
[報告のしかた](HOUKOKU.md)を見て知らせてください。報告をもとに、様式と手順を直します。
出典を確かめ直す物は、`python tools/kakunin.py --fetch` で一覧にできます。

## ライセンス

コード(`.py`、`.js`、`.css`、`.toml`)は AGPL-3.0-or-later(全文は [COPYING](COPYING))、
それ以外(文書、様式、項目、見本のデータ、画像)は CC BY 4.0 です。詳しくは [LICENSE](LICENSE) に
あります。CC BY 4.0 の物を使うときは、出典を書いてください。
役所の様式や書き方を元にした物は、それぞれのフォルダーの README に出典を書いています。

AGPL では、コードを変えて、ネットワークを通して人に使ってもらうとき(申し込みのサーバーや、
お問い合わせの関数など)は、使う人に、変えたコードを渡せるようにする必要があります。
このリポジトリは、国や役所が作った物ではありません。
