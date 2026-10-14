# Flet で画面を作り、足りない所は AI と補う

業務のアプリの画面と中身を、同じ Python で書く

業務用のアプリの画面は、ほとんどが Web です。Web の画面は、JavaScript か、それに型を付けた TypeScript で
書きます。一方で、データを扱う所や AI を呼ぶ所は、Python で書くことが多くあります。画面と中身で、言語が
2 つに分かれます。その間で、同じデータを 2 度扱うことになります。

## Flet とは

aiai と、天気のアプリ(AIseed Weather。気象のデータから天気図を作るツール)は、画面を Flet で作って
います。Flet は、Python で、Web、PC、スマートフォンのアプリを作る OSS です(Apache-2.0)。画面も中身も、
同じ Python で書けます。

## 機能はまだ十分ではない。でも、AI と補える

Flet の機能は、まだ十分ではありません。でも、OSS で、Flutter の部品を包んだ拡張を作れるので、足りない
所は AI と一緒に補えます。天気のアプリの例です。

- **足りない部品を作った。** 気象の格子データを GPU で描く部品が無かったので、AI と一緒に Flet の拡張
  (flet-gpufield)を作りました。拡大、移動、風の粒子、等値線を部品の中で扱い、Linux の内蔵 GPU で、
  1 秒に 57〜59 コマで描けます。ほかのアプリでも使えるように、MIT で公開しています
- **不具合を見つけて、補った。** Flet 1.0.4 の `use_effect` には、後始末が一度も呼ばれない書き方が
  ありました。天気のアプリでは、再生が止まらず、だんだん速くなる不具合として出ました。AI が原因を
  見つけ、必ず後始末を呼ぶ部品(`use_task_effect`)を作りました。同じ書き方が戻ったら失敗する試験と、
  AI への決まり(スキル)にも書きました

## TypeScript の欠陥

TypeScript には、次の欠陥があります。

- **型は、動かす前に消える。** TypeScript の説明書にも、型の注釈はプログラムの動きを決して変えない、と
  あります。外から来たデータ(基幹システムの CSV、ほかの Web の答え)が型のとおりかは、動いている間は
  確かめられません。断絶の境目こそ、確かめが要る所です
- **型の仕組みは、わざと完全にしていない。** 説明書は、コンパイルのときに安全と分からない操作も通す
  所があり、型の仕組みが健全(sound)ではない、と書いています
- **同じデータの型を、2 度書く。** 中身を Python で書くと、同じデータの型を TypeScript でも書くことに
  なります。片方を直したら、もう片方も直さないといけません。言語の間に、新しい断絶ができます
- **部品の山に頼る。** 画面のためだけに、npm の部品をたくさん入れます。その部品が攻撃の的になります。
  2025 年 9 月には、自分で広がる「Shai-Hulud」という仕組みに、npm の 500 を超える部品が乗っ取られ、
  開発者の GitHub やクラウドの鍵が盗まれました
- **自分では直せない。** 型を消すことと、型の仕組みを完全にしないことは、TypeScript が「目標にしない物」
  として決めた方針です。拡張のための差し込み口(プラグイン)も、エディターでの書き心地を変えるためだけの
  物で、型の確かめ方やコンパイルの仕方は変えられません。そのうえ、コンパイラーは Microsoft が Go で書き
  直している最中で、ほかの道具から使うための API は、まだできていません

(TypeScript「The Basics」の Erased Types、https://www.typescriptlang.org/docs/handbook/2/basic-types.html 。
「Type Compatibility」の A Note on Soundness、https://www.typescriptlang.org/docs/handbook/type-compatibility.html 。
米国 CISA「Widespread Supply Chain Compromise Impacting npm Ecosystem」2025-09-23、
https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem 。
TypeScript「TypeScript Design Goals」の Non-goals、https://github.com/microsoft/TypeScript/wiki/TypeScript-Design-Goals 。
「Writing a Language Service Plugin」、https://github.com/microsoft/TypeScript/wiki/Writing-a-Language-Service-Plugin 。
Microsoft「A 10x Faster TypeScript」2025-03-11、https://devblogs.microsoft.com/typescript/typescript-native-port/ 。
typescript-go の README(API は not ready)、https://github.com/microsoft/typescript-go 。
Flet、https://github.com/flet-dev/flet 。AIseed Weather、https://github.com/aiseed-dev/weather 。
2026-10-14 に確かめました)

## Go だけより、Python と Rust で

TypeScript は、コンパイラーを Go だけで書き直す道を選びました。速さを取る代わりに、使う人が手を入れる
場所は無くなります。

速さと、手を入れられることの両方を取るなら、Python と Rust を組み合わせる形があります。

- **重い所だけを Rust で書く。** Rust は、動いている間にメモリを片付ける仕組み(ガベージコレクター)を
  持たずに動きます。Go の標準の道具では、どのアプリにもガベージコレクターが入ります
- **残りは Python のままにする。** 使う人が読んで、直して、足せます。AI も Python がいちばん得意です。
  PyO3 と maturin を使うと、Rust で書いた所を、Python の部品として呼べます
- **Python の世界では、もう広く使われている。** コードの点検の Ruff と、部品を入れる uv は、Rust で
  書かれた Python の道具です。表を扱う Polars は、Rust で書かれた計算の仕組みを、Python からも使えます。
  データを確かめる Pydantic も、2 からは確かめの中心を Rust で書いています
- **Rust は書くのが難しいが、AI が書ける。** 天気のアプリでも、速さが要る所は、この形にできます

(Rust、https://rust-lang.org/ 。Go「A Guide to the Go Garbage Collector」、https://go.dev/doc/gc-guide 。
PyO3、https://github.com/PyO3/pyo3 。Ruff、https://github.com/astral-sh/ruff 。uv、https://github.com/astral-sh/uv 。
Polars、https://github.com/pola-rs/polars 。pydantic-core、https://github.com/pydantic/pydantic-core 。
2026-10-14 に確かめました)

## まとめ

- 業務のアプリの画面を TypeScript で書き、中身を Python で書くと、言語の間に断絶ができる
- Flet なら、画面も中身も同じ Python で書ける。Web、PC、スマートフォンのアプリにもなる
- Flet の機能は、まだ十分ではない。でも、OSS なので、足りない部品や不具合は、AI と一緒に補える。
  補ったことは、試験と AI への決まりに書いておく
- TypeScript は、型が動かす前に消え、型の仕組みもわざと完全にしていない。画面のために、部品の山にも頼る。
  足りない所があっても、使う人は直す側に回れない
- 速さと柔軟さは、Go だけにするより、Python と Rust を組み合わせる方が両方取れる。重い所だけを Rust で
  書き、残りは使う人が手を入れられる Python のままにする
