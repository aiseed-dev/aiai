# aiai

履歴書、開業の届出や申請書のように、決まった様式の書類を自分で作るための、
様式・データの見本・スキルを置いています。

書類のデータは adoc の文字のファイルで書き、adoc のままやり取りします。
人も機械も読めるからです。印刷するときは、officework が様式の中の印にデータを
入れて PDF にします。印とデータの書き方は、officework の
[様式の手引き](https://github.com/aiseed-dev/officework/blob/main/docs/ja/forms-manual.adoc)にあります。

```
pip install officework
```

## 中身

| フォルダー | 中身 |
|---|---|
| [rirekisho](rirekisho/) | 履歴書の様式(厚生労働省の様式例、JIS 様式)と、見本のデータ |
| [kaigyo](kaigyo/) | 開業届と青色申告承認申請書。1 つのデータから 2 つの書類のデータを作り、受け取る側で確かめる見本 |
| [office](office/) | officework を履歴書・申請書を書くための版にする、リボンの設定とボタン |

## 報告

使って困ったこと、実際に手続きをして分かったことは、[報告のしかた](HOUKOKU.md)を
見て知らせてください。報告をもとに、様式と手順を直します。

## ライセンス

[CC BY 4.0](LICENSE) です。使うときは出典を書いてください。
