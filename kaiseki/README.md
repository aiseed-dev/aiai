# 解析の受け口(kaiseki)

読む人がどこで読み、何を探しているかを記録する仕組みです。aiai のサイトでは、記録を AI に読ませ、
ページを直し、足りないページを作ります。

| ファイル | 中身 |
|---|---|
| `kaiseki.js` | ページに置くスクリプト。表示、見ていた時間、どこまで下へ見たか、出来事(短い値つき)を送る |
| `server.py` | 受け口。標準ライブラリと SQLite。IP アドレスは記録しない |
| `test_server.py` | 受け口の確かめ(`python kaiseki/test_server.py`) |

3 つのファイルは、aiseed-dev/aiai-tools の `kaiseki/` をそのまま写した物です(`kaiseki.js` はコミット e3e2d58、
`server.py` と `test_server.py` はコミット f39a9a9)。ページのスクリプトと受け口は aiai-tools で作るので、直すときは aiai-tools を
直してから写します。

## aiai.aiseed.dev での使い方

各ページに、Cookie を置かず、受け入れるかも聞かない形(`data-ask="no"`)で置きます。`site/make_site.py` が
入れます。aiai の出来事(読んだ見出し、開いた全文、写した手引き、押したリンク、見つからなかったページ)は
`site/kaiseki-aiai.js`、サイトの中で探した言葉は `site/sagasu.js` が送ります。何を記録するかは
https://aiai.aiseed.dev/kaiseki/ に書いてあります。

```
<script src="/kaiseki.js" data-to="/kaiseki" data-ask="no" defer></script>
<script src="/kaiseki-aiai.js" defer></script>
```

## aiai.aiseed.dev での置き方

Compute Engine の VM で、systemd の `aiai-kaiseki` が `127.0.0.1:8420` で動かし、Caddy が
`https://aiai.aiseed.dev/kaiseki/v1/` を渡します。記録は `~/aiai-server/kaiseki/kaiseki.db` に書きます。

```
# /etc/systemd/system/aiai-kaiseki.service
[Unit]
Description=aiai kaiseki (analytics receiver)
After=network.target

[Service]
User=dev
Environment=KAISEKI_SITES=aiai.aiseed.dev
Environment=KAISEKI_DB=/home/dev/aiai-server/kaiseki/kaiseki.db
ExecStart=/usr/bin/python3 /home/dev/aiai/kaiseki/server.py --port 8420
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```
# /etc/caddy/aiai.caddy の aiai.aiseed.dev の中。解析の道はアクセスの記録に書かない(IP アドレスを残さないため)
handle /kaiseki/v1/* {
    skip_log
    uri strip_prefix /kaiseki
    reverse_proxy 127.0.0.1:8420
}
handle {
    reverse_proxy 127.0.0.1:8020
}
```

記録は同じ VM の上で SQLite から読むので、`KAISEKI_TOKEN` と `KAISEKI_LINK_TOKEN` は置きません。
空のときは、集計と会員の口が 403 を返すだけです。
