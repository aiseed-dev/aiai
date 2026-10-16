# サーバーの攻撃の記録(aiai で作った例)

サーバーが受けた攻撃を毎日数え、AI に所見を書かせて、本人が毎朝読むアプリです。前は、ログを AI に渡して、
何が来ているかを毎日聞いていました。毎日同じことを頼んでいたので、aiai の流れでアプリにしました。

## 流れの中で作った物

| 段 | できた物 |
|---|---|
| アプリの決まり | [SKILL.md](SKILL.md) |
| 2 今あるアプリを探す | [chousa/](chousa/)(似た仕組みを Gemini が Google 検索で調べた結果) |
| 5 今あるアプリの課題を集める | [references/kougeki-analysis.adoc](references/kougeki-analysis.adoc) |
| 6 設計書とマニュアルを作る | [docs/design.adoc](docs/design.adoc)、[docs/manual.adoc](docs/manual.adoc)、[docs/kakunin.adoc](docs/kakunin.adoc) |
| 7 実装する | [tools/kougeki.py](../../tools/kougeki.py)(サーバー)、[site/app/server_view.py](../../site/app/server_view.py)(アプリの「サーバー」のタブ) |
| 8 テストの手順を作る | [docs/test.adoc](docs/test.adoc) |

2、5、6、8 は、aiai のアプリの「作る」と同じ仕事(Gemini)で作りました。実装は、この流れより前に AI と
作ってあった物です。

初めに作った設計書とマニュアルは、動いている画面と 4 か所違っていました(接続先を書く欄、ボタンの名前、日ごとの
一覧の形、スマートフォンの形の絵)。流れの「直すとき」の順に、文書を動いている画面に合わせました。まず SKILL.md の
「決まっていること」に画面の形を足し、6 と 8 をもう一度作りました。今の設計書とマニュアルは、動いている画面と合っています。
