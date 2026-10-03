# AI とのチャットの履歴から、自分を知る

AI とのチャットの記録から、長所、得意な分野、大事にしている考え方、過去の AI で十分な答えが
出なかったやり取りの改善の提案、次に学ぶこと、長所が生きる仕事などの項目を作ります。使い方は 3 種類あります。

1. **スキル**: `SKILL.md` を、使っている AI のチャットに入れます。その AI が、自分のクラウドの履歴を
   読んで作ります。使い方は本人の自由です
2. **PC の道具の記録**: aiai のアプリが、AI の道具が本人の PC に残す記録を機械的に読み、ボタン 1 つで
   報告書を作ります
3. **書き出し**: 本人が AI のサービスから書き出したファイルを、aiai のアプリが機械的に読み、ボタン 1 つで
   報告書を作ります。書き出し方は、使っている AI に聞いてください。読めないファイルは、読めないと出します

2 と 3 は、本人の PC の上でアプリを動かしたときだけ使えます。ここに挙げた物のほかの記録を足すのも
自由です。

読むのは、結果(書いた物、作った物)ではなく、対話です。結果だけでは、どう考え、どこで迷い、どう
直したかが分かりません。対話には、AI の答えを受けて本人がどう返したかが残り、そこに長所や考え方が
出ます。アプリは、本人の発言ごとに、その前の AI の答えの初めを並べて渡します。

## AI ごとに、できることとできないこと

| | 1 スキル | 2 PC の道具の記録 | 3 書き出し |
|---|---|---|---|
| ChatGPT | できる。ベータで、ワークスペースの持ち主が有効にする | Codex: `~/.codex/history.jsonl` | ZIP |
| Claude | できる。Free から Enterprise まで。コードの実行を有効にする。フォルダーごと ZIP にして上げる | Claude Code、デスクトップアプリの Claude Code と Cowork: `~/.claude/projects/` | ZIP |
| Gemini | できる。18 歳以上、個人の Google アカウント。順に提供が広がっている途中 | Gemini CLI: `~/.gemini/tmp/<プロジェクトの印>/chats/` | Google Takeout(公式の説明は未確認) |
| Microsoft 365 Copilot | ほとんどの人はできない。試しの段階で、Microsoft Frontier Program の組織だけ。`SKILL.md` を ZIP のいちばん上に置く | できない(PC に読める記録を残すという説明が見つからない) | 個人の Microsoft アカウントなら CSV。勤め先や学校のアカウントは別の手続き。CSV の列の形は公開されていない |

アプリの「ZIP」は、Claude の形(`<名前>/SKILL.md`)です。Microsoft 365 Copilot には
`/skills/<名前>.zip?for=m365`(`SKILL.md` をいちばん上に置く形)を使います。

出典: Anthropic「Use skills in Claude」(https://support.claude.com/en/articles/12512180-use-skills-in-claude)、
Google「Create & manage skills for Gemini Apps」(https://support.google.com/gemini/answer/17094296)、
OpenAI Academy「Skills」(https://academy.openai.com/public/clubs/work-users-ynjqu/resources/skills)、
Microsoft Learn「Add custom skills to your declarative agent in Agent Builder (preview)」
(https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/agent-builder-add-skills)、
Claude Code Docs「Data usage」(https://code.claude.com/docs/en/data-usage)、
Codex「Advanced Configuration」(https://learn.chatgpt.com/docs/config-file/config-advanced)、
Gemini CLI「Session management」(https://geminicli.com/docs/cli/session-management/)、
OpenAI「Exporting your ChatGPT history and data」(https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data)、
Anthropic「Export your Claude data」(https://support.claude.com/en/articles/9450526-export-your-claude-data)、
Microsoft「Manage your Copilot activity history in the privacy dashboard」
(https://support.microsoft.com/en-us/privacy/manage-your-copilot-activity-history-in-the-privacy-dashboard)。
2026-10-03 に確かめました。
