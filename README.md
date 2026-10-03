# aiai

AI 時代の学び方

自分の AI と一緒に、長所を探し、何を学ぶかを決め、小さなアプリを作ってみて、仕事を始める
ためのスキルです。転職の考え、AI の時代に何を学ぶか、現場の写真を AI に見せて判断を助ける
アプリから、学んだことを仕事にするための履歴書、起業の企画書、開業の届出、就農の計画、
事業の Web サイト、お客さんからの申し込みの仕組みまで、AI と一緒に自分で作ります。

主役は、本人がふだん使っている AI です。本人は、その AI にスキルを読ませ、対話しながら
作ります。aiai は、そのやり方と、確かめられた知識を置きます。1 つの AI だけに頼らないように、
ほかの会社の AI のモデルに見てもらうセカンドオピニオン([soudan](soudan/))も、研究として、
募集に応じた人に使ってもらう形で用意しています。

使い方は、[使い方の手引き](TSUKAIKATA.md)にまとめています。

## 使う人と一緒に育つ

このリポジトリは、使う人と一緒に育っていきます。コードは AI がほぼ無料で書けるので、スキルと
知識は有料にせず、使う人の報告で育てます。

- 実際に手続きをした人の報告で、様式、手順、スキルを直します
- 制度や金額は変わります。書いてある事実には出典と確かめた日を付け、`tools/kakunin.py` で
  確かめ直す物を一覧にします。変わっていたら、「新しい情報」として知らせてもらい、直します
- 報告するのは、公開されている内容だけです。識別情報(下の「AI は、本人が考えることを助ける」に
  あります)は書きません

報告のしかたは [HOUKOKU.md](HOUKOKU.md) にあります。

## 考え方

### 中心はスキル

各フォルダーの `SKILL.md` が、このリポジトリの中心です。何を作るか、何を守るか、どう確かめるかを
書いてあります。AI に読ませると、AI が本人に聞きながら、書類や仕組みを一緒に作ります。

- プログラムは、スキルがあれば、本人が使っている AI が本人の事情に合わせて作れます
- ただ、いまは変わり目なので、要る所ではプログラムも置いています
  - 確かめ済みの物: 間違えると危ない物(申し込みのサインインの確かめ)と、出す側と受け取る側で
    同じでないと困る物(`tools/todoke.py`)
  - 動く例: それ以外のプログラム。作り直してかまいません
- docx や xlsx を開いて直す [officework](https://github.com/aiseed-dev/officework) も、この変わり目に
  要るプログラムです。aiai では作らず、別のプロジェクトとして公開された版を使い、リボンの設定と
  ボタンの簡易版(`office/`)だけを置きます

### 書く内容は本人と AI に任せ、aiai は知識を扱う

志望動機や事業の説明のように、どういう内容を書くかは、本人と、本人が使っている AI に任せます。
書く内容の見本や手本は、その AI が本人の事情に合わせて作れるので置きません。

aiai が扱うのは、知識になっている物です。

- 様式と、その欄の決まり(記入上の注意、欄の書き方、出す先、期限など)
- 手続きの流れ、制度、金額、研究のように、出典で確かめられる事実。出典と確かめた日を付けます

### AI は、本人が考えることを助ける

- 答えを先に出しません。何のための項目か、選ぶと何が変わるかを伝え、本人に 1 つずつ聞きます
- 文は、本人が書いた言葉から下書きし、本人が直します。本人が言っていないことは足しません
- 本人にしか決められないこと(青色申告にするか、など)は、本人が決めます
- 識別情報(氏名、住所、電話、生年月日、個人番号、メールアドレスのように、誰のことか分かる
  情報)は、出さなくて済む物は出しません。ただし、事業をするには氏名、住所、電話を出す場面が
  あります(開業届に書く、通信販売の広告には事業者の氏名、住所、電話番号の表示が要る、など)。
  どこまで出すか、AI に渡すかは、本人が決めます。渡さなくても書類は作れるように、どの書類でも
  同じ氏名や住所は、AI を通さずにコード(`tools/todoke.py`)が写します。AI に渡した物が学習に
  使われるかは、そのサービスの利用規約で確かめます
- 個人番号だけは AI に渡しません。他人の個人番号を集めることは番号法第 20 条で禁じられて
  いて、AI のサービスはその例外に入らないからです
- このリポジトリはみんなの物なので、識別情報も、事業の実際の値も入れません。入れるのは
  架空の見本だけです。自分の物は、手元のファイルに置きます

出典: 消費者庁「通信販売」(https://www.no-trouble.caa.go.jp/what/mailorder/)、
個人情報保護委員会「生成 AI サービスの利用に関する注意喚起等」
(https://www.ppc.go.jp/news/careful_information/230602_AI_utilize_alert/)、
番号法(https://laws.e-gov.go.jp/law/425AC0000000027)。2026-09-28 に確かめました。

### AI を使い込んだ経験を、ソフトウェアの外の仕事に活かす

- 転職を考えるときは、いつも使っている AI に、これまでのチャットから自分の長所を探して
  もらうことから始めます。チャットには、自分で考えたことや、解いた問題が残っています。
  自分で自分の長所を探す仕組みなので、仕事を紹介する転職エージェントとは、役割が違います。
  その後、実際に AI を使って、行きたい仕事で使う小さなアプリを作る体験をし、そこで分かった
  ことも入れて、次の行動を決めます。
  手順は [tenshoku/SKILL.md](tenshoku/SKILL.md) にあります。高校生と大学の 1 回生が、AI の時代に何を
  学ぶかを考えるときも、同じ考え方で進めます([gakusei/SKILL.md](gakusei/SKILL.md))
- 狭義のソフトウェア開発は、汎用の LLM がとても安くできます。aiai は、この現実から助言します。
  ソフトウェア開発の中で居場所を探し直すより、AI を使い込んだ経験を、ものづくり、サービス、
  店、農業、空き家や民泊の運営のような、ソフトウェアの外の仕事に活かすことを考えます。
  勤めることも、自分で始めることも入ります
- 考えを整理して終わりにせず、次にする行動を決めて終えます

短い期間で作った実例です。

- Anthropic の研究者が、16 の Claude のエージェントに C のコンパイラーを Rust で一から書かせ、
  約 2 週間、API の費用 2 万米ドル弱で、約 10 万行のコンパイラーができました。Linux 6.9 を
  ビルドできます(2026-02-05)
- Cursor では、数百のエージェントを約 1 週間動かし、Web ブラウザーを一から書かせました。
  1,000 のファイルで、100 万行を超えます。同じ仕組みで、Cursor 自身のコードの Solid から
  React への書き換えを、約 3 週間で行いました(2026-01-14)
- Airbnb は、約 3,500 のテストのファイルを Enzyme から React Testing Library へ書き換える
  仕事を、人の手なら 1 年半と見積もっていた所、LLM を使って 6 週間で終えました。人の手で
  直したのは 100 ファイル足らずでした(2025-03-28 の記事)
- Google は、JUnit3 から JUnit4 への書き換えで、5,359 のファイル、14 万 9 千行を超える変更を
  3 か月で行いました。AI が作った変更の約 87% は、そのまま取り込まれました。進みを決めたのは、
  人が変更を確かめる速さでした(2025-01-12)
- Amazon は、Java 17 へ上げる仕事が、1 つのアプリにつき約 50 人日から数時間になり、
  4,500 人年分の仕事が省けたと、社長が書いています(2024-08-24、会社の発表)

出典: Anthropic「Building a C compiler with a team of parallel Claudes」
(https://www.anthropic.com/engineering/building-c-compiler)、
Cursor「Scaling long-running autonomous coding」(https://cursor.com/blog/scaling-agents)、
InfoQ の Airbnb の記事(2025-03-28)
(https://www.infoq.com/news/2025/03/airbnb-llm-test-migration/)、
Nikolov ほか「How is Google using AI for internal code migrations?」(https://arxiv.org/abs/2501.06972)、
Simon Willison による Andy Jassy の投稿の引用(https://simonwillison.net/2024/Aug/24/andy-jassy-amazon-ceo/)。
2026-10-02 に確かめました。

AI は、文字だけでなく、写真や映像も読めます。画像や映像を読んで言葉で答える AI のモデルを
VLM と呼びます。ものづくり、店、農業、空き家や民泊、ジムのような実物を扱う仕事では、多くの
判断を目で見て行っています。現場で撮った写真を VLM に見せると、AI をその判断に使えます。
何を見るかを決め、AI の答えを確かめるのは、現場の知識を持つ人です。手順は
[genba/SKILL.md](genba/SKILL.md) にあります。

人が検索ではなく AI に聞くようになると、AI が読んで正しく使える中身(確かな事実、出典、
決まった形のデータ)が力になります。AI がそれを読んでまとめ、人に答えるからです。これまで
情報を出す側がお金をかけてきたサイトや検索の仕組み、アプリの画面は、人が見なくなります。

- 米国の大人 900 人の、2025 年 3 月の Google の検索 68,879 回を調べた Pew Research Center の
  調査では、AI の要約が出たときに検索の結果のリンクを押したのは 8% で、出なかったときの 15% の
  約半分でした。AI の要約の中のリンクを押したのは 1% でした(2025-07-22)
- Similarweb と Axios のデータによると、米国の主なニュースのサイト約 100 への訪問は、2024 年の
  7,000 万回超から、2026 年 7 月の 4,760 万回に減りました(TIME、2026-09-29)

出典: Pew Research Center「Google users are less likely to click on links when an AI summary
appears in the results」
(https://www.pewresearch.org/short-reads/2025/07/22/google-users-are-less-likely-to-click-on-links-when-an-ai-summary-appears-in-the-results/)、
TIME(2026-09-29、https://time.com/article/2026/09/29/google-search-ai-mode-chat)。
2026-10-02 に確かめました。

Linux のカーネルの開発も、AI を使うことを前提にしています。

- カーネルの公式の文書に、AI を使うときの決まりがあります。AI の手を借りたパッチには、
  使った AI を `Assisted-by:` の行に書きます。開発者の証明(Signed-off-by)を付けられるのは
  人だけで、AI が書いたコードを確かめて責任を負うのは、出した人です
- Linus Torvalds は、カーネルのメーリングリストで、Linux は AI に反対するプロジェクトでは
  ないと書きました(2026-07 の報道)。Linux 7.2 の開発では、AI の道具のレビューから出た
  直しが多く、大きな更新が普通になったと書いています(2026-08 の報道)
- 安定版の保守では、取り込むパッチの候補を LLM で絞り込んでいます(2025-06 の講演)

出典: The Linux Kernel documentation「AI Coding Assistants」
(https://docs.kernel.org/process/coding-assistants.html)、
Virtualization Review(2026-07-16、https://virtualizationreview.com/articles/2026/07/16/linus-torvalds-says-linux-kernel-is-not-an-anti-ai-project.aspx)、
The Register(2026-08-10、https://www.theregister.com/os-platforms/2026/08/10/linus-torvalds-says-ai-has-made-huge-linux-kernel-updates-the-new-normal/5285268)、
LWN.net「Supporting kernel development with large language models」(2025-06-26、https://lwn.net/Articles/1026558/)。
2026-10-02 に確かめました。

### 公開のリポジトリに絶対に入れない物

次の物は、1 度 push すると、消しても漏れた物として扱う必要があります。

- API のトークンと鍵。AWS のアクセスキー、Google Cloud のサービスアカウントの JSON の鍵、
  Cloudflare の API トークン、Apple のサインインの鍵(`.p8`)、Anthropic や OpenAI の API キー
- パスワードが入った接続文字列。`postgresql://ユーザー:パスワード@ホスト/データベース` のような物
- `.env` のファイルと、compose や設定に直に書いたパスワードや秘密の値(`GOOGLE_CLIENT_SECRET`、
  `TURNSTILE_SECRET`、`JWT_SECRET` など)
- SSH の秘密鍵(`id_ed25519` など)と、TLS の秘密鍵(`.pem`、`.key`)
- お客さんの識別情報が入るデータベースのファイル(`moushikomi.db`、`soudan.db` など)

秘密の値は、環境の変数か、サーバーにだけ置く `.env` で渡します。リポジトリには `.env.example`
(値は `変えてください`)だけを入れます。GitHub には、対応している秘密の値を push の前に止める
機能(push protection)があり、個人のアカウントでは最初から有効です。それでも、止められる物は
一部なので、頼り切りません。入ってしまったときは、まずそのトークンや鍵を無効にして
作り直します。履歴から消すだけでは足りません。

出典: GitHub Docs「Push protection」
(https://docs.github.com/en/code-security/concepts/secret-security/push-protection)、
「Removing sensitive data from a repository」
(https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。
2026-09-28 に確かめました。

### 書類のファイルの形

書類のデータは、adoc という文字のファイルで書きます。テキストエディターで開けて、
GitHub の画面では表になります。表計算やワープロのソフトは要りません。

## 中身

| フォルダー | 中身 |
|---|---|
| [kaigyo](kaigyo/) | 開業届と青色申告承認申請書の項目(国税庁の様式と照らし合わせ済み)、見本のデータ、受け取る側の見本 |
| [nougyou](nougyou/) | 農業を始めるときの手続き(出典と確かめた日付き)、青年等就農計画の項目と見本のデータ |
| [nougyou/keikaku](nougyou/keikaku/) | 自然農法の経営計画を作るスキル。自然農法系の農業の紹介(いいことと難しいこと)と、年ごとの計算 |
| [rireki](rireki/) | AI とのチャットの記録から自分を知る。12 の項目を、3 種類のやり方で作る: スキル(ChatGPT、Claude、Gemini、Microsoft 365 Copilot のチャットに入れる)、PC の AI の道具の記録をアプリが読む、書き出したファイルをアプリが読む。AI ごとのできることとできないことは [rireki/README.md](rireki/README.md) |
| [tenshoku](tenshoku/) | 転職を考えるときに、これまでのチャットから自分の長所を AI に探してもらい、ソフトウェアの外の仕事に活かす道を考え、AI でアプリを作る体験をして、次の行動を決めるスキル |
| [gakusei](gakusei/) | AI の時代、何を学ぶか。高校生と大学の 1 回生が、これまでのチャットから自分の長所を AI に探してもらい、AI でアプリを作る体験をして、何を学び、何をするかを決めるスキル |
| [genba](genba/) | 現場で撮った写真を VLM(画像を読む AI)に見せて、仕事の判断を助ける小さなアプリを作るスキル。何を見るかは本人が決め、AI の答えは人が確かめて記録する |
| [rirekisho](rirekisho/) | 履歴書の様式(厚生労働省の様式例、JIS 様式)と、欄の決まり |
| [website](website/) | 事業の Web サイトを作るスキル。開業届と同じデータから公開してよい事実だけを写し、Cloudflare Pages で公開する。名前の要らないお問い合わせは Cloudflare の Workers と R2 で受ける |
| [moushikomi](moushikomi/) | Apple ID か Google ID でサインインした人から、申し込み(取り置き、予約、注文など)を受けるスキルと仕組み。預かる項目を adoc に書き、画面は Flet で作る |
| [news](news/) | aiai ニュース。空き家、民泊、クライミングジムなどに共通する、VLM、スマートドア、スマートロック、鳥獣対策のニュースを毎日まとめる |
| [soudan](soudan/) | セカンドオピニオン(研究として、募集に応じた人だけが使う)。自分の AI と作った転職の考え、何を学ぶかの考え、履歴書、起業の企画書を、ほかの会社の AI のモデルに見てもらい、相談と出来事を記録する(試作) |
| [office](office/) | officework の簡易版。書類を書いて直すための、リボンの設定ファイルと Python のボタンだけ |
| [site](site/) | aiai のサイトとアプリ。トップページは HTML と CSS、`/app/` は Flet の画面(スキルの一覧、写してあなたの AI に貼る、考え方、お知らせ)。同じ画面を `flet build` でアプリにできる形にしている |
| [tools](tools/) | `todoke.py`(書類ごとのデータを作る、受け取って確かめる)、`kakunin.py`(出典を確かめ直す物を出す)、`houkoku.py`(報告の下書き)、`office_kit.py`(office のボタンが使う) |

見本の人、店、数字は、すべて架空です。

## 使う物

| 使う所 | 要る物 |
|---|---|
| `tools/todoke.py`、`tools/kakunin.py`、`nougyou/keikaku/keikaku.py`、`website/sample/build.py` | Python 3 だけ(Python 3.9 で確かめました) |
| `moushikomi/` | Python 3 と、conda-forge の `fastapi`、`uvicorn`、`pyjwt`、`cryptography`、`flet`、`python-multipart`、`websockets`。Web の画面には pip の `flet-web`(Python 3.14 で確かめました) |
| `soudan/` | `moushikomi/` と同じ部品(画面の `flet` と `flet-web` を除く)。本物のモデルを使うときは、各社の公式の SDK(Anthropic なら `anthropic`) |
| `site/` | `moushikomi/` と同じ部品(`fastapi`、`uvicorn`、`flet`、`flet-web`、`websockets`)。先に `python site/make_assets.py` でスキルをアプリの中に写す |
| `website/` の公開とお問い合わせ | Cloudflare のアカウント(無料のプランで使えます) |
| 様式を埋めて PDF にする、`tools/houkoku.py`、`office/` | [officework](https://github.com/aiseed-dev/officework)。印とデータの書き方は、officework の [様式の手引き](https://github.com/aiseed-dev/officework/blob/main/docs/ja/forms-manual.adoc)にあります |

aiai が使う officework の機能(様式を埋める `Book.fill` と、リボンの設定ファイル)は、いま PyPI に
ある officework 0.7.0 には、まだ入っていません。officework で機能が足りないときやバグは、
officework の Issues に報告します。

## いまの状態

- 動かして確かめた物: `tools/todoke.py`、`tools/kakunin.py`、`nougyou/keikaku/keikaku.py`、
  `website/sample/build.py`、`moushikomi/`(偽の Apple と Google を相手にしたテストと、Web の画面を
  押して確かめること)、`soudan/`(偽の Apple と Google、偽のモデルを相手にしたテスト)、
  `site/`(トップページとアプリの画面を、ブラウザーで押して確かめること。セカンドオピニオンの
  タブは、偽の Apple と Google、偽のモデルで)
- まだ確かめていない物:
  - Cloudflare Pages での公開と、お問い合わせの関数
  - `moushikomi/` を本物の Apple と Google で使うこと。iPhone と Android のアプリへの書き出し
  - `soudan/` を本物のモデルにつなぐこと
  - aiai のサイトの公開(aiai.aiseed.dev)と、アプリへの書き出し(`flet build`)
  - `office/` の Linux と Windows での動き
  - `tenshoku/`、`gakusei/`、`genba/` のスキルを、実際に人と AI で通して使うこと
- これから作る物:
  - `kaigyo/` と `rirekisho/` の `SKILL.md`(いまは、開業届では `todoke.py` が AI への依頼の文を書きます)
  - 起業の企画書を、本人の AI と対話しながら作るスキル(`soudan/観点/企画書.md` は、見る観点だけです)
  - 自然農法の経営計画に、福岡正信の著作からの引用

## ライセンス

コード(`.py`、`.js`、`.css`、`.toml`)は AGPL-3.0-or-later(全文は [COPYING](COPYING))、
それ以外(文書、様式、項目、見本のデータ、画像)は CC BY 4.0 です。詳しくは [LICENSE](LICENSE) に
あります。CC BY 4.0 の物を使うときは、出典を書いてください。
役所の様式や書き方を元にした物は、それぞれのフォルダーの README に出典を書いています。

AGPL では、コードを変えて、ネットワークを通して人に使ってもらうとき(申し込みのサーバー、
セカンドオピニオンのサーバー、お問い合わせの関数など)は、使う人に、変えたコードを渡せるようにする必要があります。
このリポジトリは、国や役所が作った物ではありません。
