# aiai で作った例: サーバーの攻撃の記録

AI に毎日頼んでいたことを、aiai の流れでアプリにした例です

aiai のサーバーは、毎日、知らない相手から SSH で入ろうとされ、穴を探す要求を受けています。前は、そのログを
AI に渡して、何が来ているか、手を打つことはあるかを、毎日聞いていました。毎日同じことを頼んでいたので、
アプリにしました。毎日 0 時過ぎにサーバーが攻撃を数え、Gemini が所見を書き、本人が毎朝、アプリの「サーバー」の
タブで読みます。

このアプリを、aiai の流れに沿って見直しました。2、5、6、8 の段は、aiai のアプリの「作る」と同じ仕事(Gemini)で
作りました。できた物は、すべてリポジトリの `kanri/kougeki/` にあります。

## 流れの中で作った物

| 段 | できた物 |
|---|---|
| アプリの決まり | [SKILL.md](https://github.com/aiseed-dev/aiai/blob/main/kanri/kougeki/SKILL.md)。使う人、数える物、記録の置き場、AI に渡す物、完成の基準 |
| 2 今あるアプリを探す | [調べた結果](https://github.com/aiseed-dev/aiai/blob/main/kanri/kougeki/chousa/2026-10-16.adoc)。Google Cloud Security Command Center、Logwatch、CrowdSec の 3 つを、Gemini が Google 検索で公式サイトなどを読んで比べました |
| 5 今あるアプリの課題を集める | [課題の資料](https://github.com/aiseed-dev/aiai/blob/main/kanri/kougeki/references/kougeki-analysis.adoc)。3 つの問題点と、作るアプリで防ぐこと 10 項目 |
| 6 設計書とマニュアルを作る | [設計書](https://github.com/aiseed-dev/aiai/blob/main/kanri/kougeki/docs/design.adoc)、[利用者マニュアル](https://github.com/aiseed-dev/aiai/blob/main/kanri/kougeki/docs/manual.adoc)、[照らし合わせの記録](https://github.com/aiseed-dev/aiai/blob/main/kanri/kougeki/docs/kakunin.adoc) |
| 7 実装する | [tools/kougeki.py](https://github.com/aiseed-dev/aiai/blob/main/tools/kougeki.py)(サーバー)と、アプリの「サーバー」のタブ |
| 8 テストの手順を作る | [テストの手順](https://github.com/aiseed-dev/aiai/blob/main/kanri/kougeki/docs/test.adoc) |

課題の資料の「作るアプリで防ぐこと」には、たとえば次の項目があります。

- サーバーの記録をそのまま外のサービスや AI に渡さない
- 通信の遮断など、サーバーの動きに自動で手を加えない
- サーバーに AI を呼ぶための鍵のファイルを置かない
- 報告のためにメールの送信のソフトなどを足さない

## 設計書と、動いているアプリの違い

このアプリは、流れより前に AI と作って動かしていました。できた設計書と利用者マニュアルを、動いている
「サーバー」のタブと比べると、次の違いがありました。

- 接続先: マニュアルには「サーバーの接続先」を書く欄があります。動いているタブには欄が無く、設定で決めます
- ボタン: マニュアルは「記録を写す」です。動いているタブは「サーバーから取り込む」です
- 日ごとの一覧: マニュアルは日付を選ぶ欄です。動いているタブは、日ごとの数を並べた表で、日付を押して開きます
- 画面の絵: スマートフォンの形で描かれています。このタブは、本人の PC で使います

違いは、流れの「直すとき」の順に直します。どちらに合わせるかを決め、まず SKILL.md を直し、設計書と
マニュアルを作り直してから、アプリを直します。
