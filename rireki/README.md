# 度々聞いていることを、アプリにする

AI とのチャットの履歴から、度々聞いていること、頼んでいることを見つけ、小さなアプリにします。
暮らしにも仕事にも使えます。何度も同じ直しをしている物は、アプリにせず、AI への決まりに書きます。
使い方は 3 種類あります。

1. **スキル**: `SKILL.md` を、使っている AI のチャットに入れます。その AI が、自分のクラウドの履歴を
   読んで進めます
2. **PC の道具の記録**: aiai のアプリが、AI の道具が本人の PC に残す記録を機械的に読み、ボタン 1 つで
   材料のファイル(このスキルと、識別情報を伏せた対話の資料が 1 つになった物)を作ります。本人は、
   そのファイルを使っている AI のチャットに上げます
3. **書き出し**: 本人が AI のサービスから書き出したファイルを、aiai のアプリが機械的に読み、2 と同じ
   材料のファイルを作ります。書き出し方は、使っている AI に聞いてください。読めないファイルは、読めないと出します

どのやり方でも、数えて並べるのも、アプリを作るのも、本人の AI です。2 と 3 は、本人の PC の上で
アプリを動かしたときだけ使えます。

## AI ごとに、できることとできないこと

| | 1 スキル | 2 PC の道具の記録 | 3 書き出し |
|---|---|---|---|
| ChatGPT | できる。ベータで、ワークスペースの持ち主が有効にする | Codex: `~/.codex/history.jsonl` | ZIP |
| Claude | できる。Free から Enterprise まで。コードの実行を有効にする。フォルダーごと ZIP にして上げる | Claude Code、デスクトップアプリの Claude Code と Cowork: `~/.claude/projects/` | ZIP |
| Gemini | できる。18 歳以上、個人の Google アカウント。順に提供が広がっている途中 | Gemini CLI: `~/.gemini/tmp/<プロジェクトの印>/chats/` | Google Takeout(公式の説明は未確認) |
| Microsoft 365 Copilot | 企業用の場合は、管理者に言ってもらってください。スキル(Agent Builder)は試しの段階で、組織が Microsoft Frontier Program に入っていて、Copilot のライセンスがあること。使えるエージェントは管理者が決める。Information Barriers を使う組織では使えない | 企業用の場合は、管理者に言ってもらってください(PC に読める記録を残すという説明が見つからない) | 企業用の場合は、管理者に言ってもらってください。履歴(プロンプトと答え)は組織のコンテンツとして保存され、管理者が Content search と Microsoft Purview で見られ、保持の期間を決める。本人は消せるが、本人が書き出す手順は見つからない。個人の Microsoft アカウントなら、プライバシーダッシュボードから CSV |

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
(https://support.microsoft.com/en-us/privacy/manage-your-copilot-activity-history-in-the-privacy-dashboard)、
Microsoft Learn「Data, Privacy, and Security for Microsoft Copilot」
(https://learn.microsoft.com/en-us/microsoft-365/copilot/microsoft-365-copilot-privacy)。
2026-10-03 に確かめました。
