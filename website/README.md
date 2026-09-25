# Web サイト

自分の事業の Web サイトを、adoc のページから作るスキルです。見本は、
kaigyo の見本と同じ架空のパン屋「はなこパン」のサイトです。

AI に [SKILL.md](SKILL.md) を読ませると、AI が本人に聞きながらページを一緒に書きます。
屋号、住所、電話、営業時間は、開業届と同じ `事業.sheet.adoc` から写すので、
もう一度書かなくて済みます。

## かかる費用

- 作るとき: AI の利用料
- 公開: Cloudflare Pages の無料のプランで使えます。無料のプランでは、サイトを作るのは
  月に 500 回まで、ファイルは 20,000 個まで、1 つのファイルは 25 MiB までです
- お問い合わせ: Workers と R2 の無料の枠で受けられます。お問い合わせを受ける関数の呼び出しは、
  Workers の無料のプランと合わせて 1 日 100,000 回まで、R2 の保存は月に 10 GB まで、
  書き込みは月に 100 万回までです。ページを見るだけでは、関数は呼ばれません
- 独自のドメイン(`example.jp` のような名前)を使うときは、その費用がかかります

公開には Cloudflare Pages を使います。GitHub Pages は Microsoft のサービスで、古い技術であり、
最近の進歩が取り入れられていない、Cloudflare の方がはるかに進んでいる、と発注者は
判断しています。

出典: Cloudflare Docs「Limits」(https://developers.cloudflare.com/pages/platform/limits/)、
「Git integration」(https://developers.cloudflare.com/pages/get-started/git-integration/)、
「Build image」(https://developers.cloudflare.com/pages/configuration/build-image/)、
「Pages Functions pricing」(https://developers.cloudflare.com/pages/functions/pricing/)、
「Routing」(https://developers.cloudflare.com/pages/functions/routing/)、
「Bindings」(https://developers.cloudflare.com/pages/functions/bindings/)、
「R2 pricing」(https://developers.cloudflare.com/r2/pricing/)、
「Turnstile server-side validation」
(https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)。
2026-09-25 に確かめました。

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
| `sample/pages/contact.adoc` | お問い合わせのページ |
| `sample/functions/api/contact.js` | お問い合わせを受け、1 件ずつ R2 に入れる関数(Cloudflare Pages Functions) |

サイトのリポジトリは公開されます。`Webサイト.sheet.adoc` には、公開してよい事実だけを
入れます。氏名、生年月日、個人番号は入れません。

## 確かめたこと

- `build.py` で見本のサイトを作り、ブラウザーで 4 ページとお知らせを開きました。
  スマートフォンの幅(375 ピクセル)で横に崩れないこと、明るい画面と暗い画面の両方で
  読めることを確かめました(Python 3.9、macOS)
- お問い合わせのページを、スマートフォンの幅で開き、横に崩れないこと、送った後と
  送れなかったときの知らせが出ることを確かめました(`#sent`、`#error` を付けて開く)
- Cloudflare Pages での公開と、`functions/api/contact.js` は、まだ実際には動かしていません。
  手元に Node.js が無く、Cloudflare の道具(wrangler)で試せていないためです
