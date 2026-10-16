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
作ってあった物です。設計書とテストの手順と照らし合わせて、違う所は直していきます。
