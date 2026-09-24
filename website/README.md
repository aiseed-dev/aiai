# Web サイト

自分の事業の Web サイトを、adoc のページから作るスキルです。見本は、
kaigyo の見本と同じ架空のパン屋「はなこパン」のサイトです。

AI に [SKILL.md](SKILL.md) を読ませると、AI が本人に聞きながらページを一緒に書きます。
屋号、住所、電話、営業時間は、開業届と同じ `事業.sheet.adoc` から写すので、
もう一度書かなくて済みます。

## かかる費用

- 作るとき: AI の利用料
- 公開: GitHub Pages は、公開のリポジトリなら GitHub の無料のプランで使えます
- 独自のドメイン(`example.jp` のような名前)を使うときは、その費用がかかります

## 見本を作ってみる

```
python tools/todoke.py tsukuru kaigyo/事業.sheet.adoc website/Webサイト.koumoku.adoc
python website/sample/build.py website/sample --out _site
```

1 行目は、`事業.sheet.adoc` から公開する事実(屋号、住所、電話、営業時間、定休日)だけを
`kaigyo/Webサイト.sheet.adoc` に写します。見本のフォルダーには、写した物を
入れてあります。2 行目で `_site/index.html` ができるので、ブラウザーで開きます。

## ファイル

| ファイル | 中身 |
|---|---|
| `SKILL.md` | AI への手順。聞くこと、守ること、ページの書き方 |
| `Webサイト.koumoku.adoc` | サイトに出す事実の一覧。出さない物は行を消します |
| `sample/` | 見本のサイト。このフォルダーを写すと、自分のサイトのリポジトリになります |
| `sample/build.py` | adoc のページから HTML を作るスクリプト。Python の標準ライブラリだけで動きます |
| `sample/pages/`、`sample/news/` | ページとお知らせ |
| `sample/style.css` | 見た目。色は先頭の数行で変えられます |
| `sample/.github/workflows/pages.yml` | push のたびにサイトを作って GitHub Pages に公開する設定 |

サイトのリポジトリは公開されます。`Webサイト.sheet.adoc` には、公開してよい事実だけを
入れます。氏名、生年月日、個人番号は入れません。

## 確かめたこと

- `build.py` で見本のサイトを作り、ブラウザーで 4 ページとお知らせを開きました。
  スマートフォンの幅(375 ピクセル)で横に崩れないこと、明るい画面と暗い画面の両方で
  読めることを確かめました(Python 3.9、macOS)
- `pages.yml` は、まだ GitHub の上で動かしていません
