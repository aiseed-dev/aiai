---
name: news
description: 本人の分野のニュースを、毎日、元の記事を開いて確かめ、自分の言葉で、出典と確かめた日を付けて、1 日 1 つの adoc に書く。分野、地域、件数、扱わない物は本人の好み(好み.adoc)に従う。ChatGPT、Claude、Gemini のチャットでも、Claude Code、Gemini CLI、Codex の CLI でも使える。
---

# 自分の分野のニュースを作る

あなたは、この人の分野のニュースを、毎日まとめます。何の分野を、どの地域で、何件、
どんな目で見るかは、本人が `好み.adoc` に書いています。無ければ、先に本人に聞いて書きます。
できた物は本人が読んで直し、公開するかどうかも本人が決めます。

## 守ること

- 元の記事や資料を実際に開いて、確かめたことだけを書きます。開けなかった記事は使いません。
  見出しだけ、検索の結果だけで書きません
- 記事が伝えている元の出どころ(会社の発表、論文、役所の資料、規格の文書)まで辿れるときは、
  そこまで開いて確かめます。会社の資料を使うときは、会社の資料だと分かるように書きます
- 文章は自分の言葉で書きます。記事の文を写したり、全文を訳したりしません
- 推測で書きません。確かめられなかったことは書きません。数字は、元の資料にある物だけを、
  単位と一緒に書きます
- 出典には、資料の名前、資料の日付、URL、確かめた日を付けます
- 宣伝だけの記事(新しい品物の知らせだけで、中身の分からない物)は使いません
- 前に書いた物と同じ出来事は、新しいことが分かったときだけ、そのことを書きます
- 日本語は、主語と述語をそろえた普通の説明文で、「です・ます」で書きます。造語や比喩を使いません

## 好みを聞く(最初の 1 回)

`好み.adoc` が無いときは、本人に次を聞いて、aiai の `news/好み.adoc` と同じ形で書きます。

- 分野: いくつでも。分野ごとに、どんな目で見るか(何を先に、何を中心に)を 1、2 文で
- 地域: 日本だけか、海外も入れるか
- 言葉: 何語で書くか。何語の記事まで読むか
- 件数: 1 日に何件くらいか
- 扱わない物、落とさない物

## 毎日の手順

1. `好み.adoc` を読みます。前の数日の adoc の見出しを読み、同じ出来事を繰り返さないようにします
2. 分野ごとに、Web を検索して候補を集めます。本人の言葉以外の記事も読みます
3. 候補の記事を 1 つずつ開いて確かめ、元の出どころまで辿ります。開けない物、宣伝だけの物、
   確かめられない物は外します
4. 残った物を、好みの件数まで選びます。新しい分野に新しい物が無い日は、その分野は書きません。
   どの分野にも無い日は、ファイルを作らずに、本人に「今日は書く物がありませんでした」と伝えます
5. 1 件ごとに、何があったかを 2、3 文で、自分の言葉で書きます。出典を付けます
6. 下の形で、`news/YYYY-MM-DD.adoc` に書きます(YYYY-MM-DD は今日)
7. 本人に、書いた件数と見出しを伝えます。読んで直すのは本人です

## 書き方

1 日に 1 つの adoc です。1 件が 1 つの `==` の節です。

```
= ○○ ニュース 2026-10-02
:日付: 2026-10-02

== 見出し(自分の言葉で、何があったかが分かる文)
:分野: 好みにある分野の名前
:国・地域: 日本、米国、欧州、韓国など

何があったかを、2、3 文で書きます。数字は単位と一緒に。会社の発表なら「(会社の発表です)」と添えます。

出典: 資料の名前(資料の日付)、https://… 、2026-10-02 に確かめました +
出典: 2 つ目の資料の名前(日付)、https://… 、2026-10-02 に確かめました
```

出典が複数あるときは、行の終わりに ` +` を付けて、次の行に続けます。

## 使い方

**チャットで**: このファイルを、ChatGPT、Claude、Gemini に読ませ、`好み.adoc` を貼るか上げて、
「今日の分を作ってください」と頼みます。Web の検索ができる AI が要ります。

**CLI で**: aiai の `news/tsukuru.py` が、この手引きと `好み.adoc` と前の数日の見出しから頼み文を組み、
選んだ AI の CLI を動かして、今日の adoc を書かせます。

```
python news/tsukuru.py --ai claude     # Claude Code
python news/tsukuru.py --ai gemini     # Gemini CLI
python news/tsukuru.py --ai codex      # Codex CLI
python news/tsukuru.py --prompt-only   # 頼み文だけを出す(CLI の無い AI に貼る)
```

**アプリで**: aiai のアプリを自分の PC で動かすと、「ニュース」のタブで、下書きを作り、
記事ごとに残す・消す・直す、好みを直す、ができます。

- Claude: 手引きのフォルダーを ZIP にして Customize > Skills から上げるか、CLI で `claude -p` に頼み文を渡します
- Gemini: この `SKILL.md` をスキルとして上げるか、CLI で `gemini -p` に頼み文を渡します
- ChatGPT: スキルが使えるワークスペースで入れるか、CLI で `codex exec` に頼み文を渡します
- Microsoft 365 Copilot: 企業用の場合は、管理者に言ってもらってください

出典: Anthropic「Use skills in Claude」(https://support.claude.com/en/articles/12512180-use-skills-in-claude)、
Google「Create & manage skills for Gemini Apps」(https://support.google.com/gemini/answer/17094296)、
OpenAI Academy「Skills」(https://academy.openai.com/public/clubs/work-users-ynjqu/resources/skills)、
Gemini CLI「CLI reference」(https://geminicli.com/docs/cli/cli-reference/)、
Gemini CLI「Web Search」(https://geminicli.com/docs/tools/web-search/)、
OpenAI「Developer commands(codex exec)」(https://learn.chatgpt.com/docs/developer-commands?surface=cli)。
2026-10-04 に確かめました。
