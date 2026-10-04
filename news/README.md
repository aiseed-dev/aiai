# aiai ニュース

自分の分野のニュースを、毎日、自分の AI にまとめさせる所です。aiai のニュース
(https://aiai.aiseed.dev/news/)は、その見本で、VLM、スマートドア、スマートロック、鳥獣対策の
4 つを、日本と海外から集めています。

| ファイル | 中身 |
|---|---|
| `SKILL.md` | 手引き。守ること、好みの聞き方、毎日の手順、adoc の書き方。ChatGPT、Claude、Gemini のチャットでも、CLI でも使えます |
| `好み.adoc` | aiai の好み(分野と分野ごとの見る目、地域、言葉、件数、扱わない物、落とさない物)。自分のニュースを作る人は、これを写して書き替えます |
| `tsukuru.py` | 手引きと好みと前の数日の見出しから頼み文を組み、選んだ AI の CLI(Claude Code、Gemini CLI、Codex)を動かして、今日の adoc を書かせます。できたファイルの形も確かめます。標準ライブラリだけ |
| `YYYY-MM-DD.adoc` | 1 日 1 つのニュース。1 件が 1 つの `==` の節で、分野、国・地域、本文、出典(資料の名前、日付、URL、確かめた日)が入ります |

## 作り方

```
python news/tsukuru.py --ai claude     # Claude Code で今日の分を書かせる
python news/tsukuru.py --ai gemini     # Gemini CLI で
python news/tsukuru.py --ai codex      # Codex CLI で
python news/tsukuru.py --prompt-only   # 頼み文だけを出す(CLI の無い AI に貼る)
```

できた `news/YYYY-MM-DD.adoc` を人が読んで直してから、コミットします。aiai のサイトには、
コミットした物だけが載ります(`site/make_site.py` が adoc からページを作ります)。
aiai のアプリを自分の PC で動かすと、「ニュース」のタブで、下書きを作り、記事ごとに
残す・消す・直すことができます。

実際に動かして確かめたのは Claude Code です(2026-10-04)。Gemini CLI と Codex の動かし方は、
公式の資料で確かめた物で、まだ実際には動かしていません。

## 書くときの決まり

`SKILL.md` の「守ること」にあります。元の記事を実際に開いて確かめたことだけを、自分の言葉で、
出典と確かめた日を付けて書きます。宣伝だけの記事は使いません。推測で書きません。
