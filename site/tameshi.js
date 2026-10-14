// SPDX-License-Identifier: AGPL-3.0-or-later
// /tameshi.html: try aiai with Gemini after signing in (tameshi/server.py at
// /tameshi). The sign-in comes back with a one-time code in the address,
// which is traded for a session token kept in this tab only.
(function () {
  var API = "/tameshi", KEY = "aiai.tameshi.token";
  var $ = function (id) { return document.getElementById(id); };
  var token = "";
  try { token = sessionStorage.getItem(KEY) || ""; } catch (e) {}
  var dialogue = [];

  function call(path, body) {
    var opts = { headers: {} };
    if (token) opts.headers.Authorization = "Bearer " + token;
    if (body) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(API + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) {
          var msg = d.detail || "うまくいきませんでした(" + r.status + ")";
          if (r.status === 401) signedOut();
          throw new Error(Array.isArray(msg) ? msg.join("、") : msg);
        }
        return d;
      });
    });
  }
  function keep(t) {
    token = t;
    try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY); } catch (e) {}
  }
  function signedOut() {
    keep("");
    $("tameshi-in").hidden = false;
    $("tameshi-use").hidden = true;
    if (PLACES[aim]) note("tameshi-in-note", "サインインすると、「" + PLACES[aim] + "」に進みます");
  }
  function note(id, text, bad) {
    var el = $(id);
    el.textContent = text || "";
    el.classList.toggle("bad", !!bad);
  }
  function left(d) {
    if (d && d.left !== undefined) $("tameshi-left").textContent = "今日あと " + d.left + " 回";
  }

  // A step of the flow on the top page links here (/tameshi.html#chousa). Go there once
  // signed in, also after the trip to Apple or Google, which drops the #.
  var GOTO = "aiai.tameshi.goto", PLACES = { chousa: "今あるアプリを探す", kaizen: "どう良くするかを考える",
    kadai: "今あるアプリの課題を集める", sekkei: "設計書と利用者マニュアルを作る" };
  var aim = location.hash.slice(1);
  try {
    if (PLACES[aim]) sessionStorage.setItem(GOTO, aim);
    else aim = sessionStorage.getItem(GOTO) || "";
  } catch (e) {}
  function arrive() {
    if (!PLACES[aim]) return;
    try { sessionStorage.removeItem(GOTO); } catch (e) {}
    var place = $(aim);
    aim = "";
    if (!place || place.closest("[hidden]")) return;
    place.scrollIntoView({ block: "start", behavior: "instant" });
    var box = place.querySelector("input[name=name], textarea");  // the first field to type in
    if (box) box.focus({ preventScroll: true });
  }

  function signedIn() {
    return call("/api/me").then(function (me) {
      $("tameshi-in").hidden = true;
      $("tameshi-use").hidden = false;
      $("tameshi-who").textContent = me.provider === "test" ? "テストアカウント" : (me.email || me.provider);
      $("tameshi-left").textContent = "今日あと: 対話 " + me.left.chat + " 回、ニュース " + me.left.news + " 回、アプリ探し "
        + me.left.chousa + " 回、課題 " + me.left.kadai + " 回、設計書 " + me.left.sekkei + " 回";
      $("tameshi-kaihatsu").hidden = !me.kaihatsu;
      arrive();
    });
  }

  // Back from Apple or Google with ?code=
  var url = new URL(location.href), one = url.searchParams.get("code");
  var ready = Promise.resolve();
  if (one) {
    url.searchParams.delete("code");
    history.replaceState(history.state, "", url.toString());
    ready = call("/api/session", { code: one }).then(function (d) { keep(d.token); })
      .catch(function (e) { note("tameshi-in-note", e.message, true); });
  }

  call("/api/info").then(function (info) {
    ["google", "apple"].forEach(function (p) {
      var b = $("tameshi-" + p);
      b.hidden = info.providers.indexOf(p) < 0;
      b.href = API + "/login/" + p + "?next=" + encodeURIComponent(location.origin + location.pathname);
    });
    $("tameshi-test").hidden = !info.test_login;
    if (PLACES[aim] && !token && !one) note("tameshi-in-note", "サインインすると、「" + PLACES[aim] + "」に進みます");
    var sel = $("tameshi-guide");
    info.guides.forEach(function (g) {
      var o = document.createElement("option");
      o.value = g.name;
      o.textContent = g.title;
      if (g.name === "rireki") o.selected = true;
      sel.appendChild(o);
    });
    return ready.then(function () { return token ? signedIn().catch(function () {}) : null; });
  }).catch(function (e) { note("tameshi-in-note", "いまは使えません: " + e.message, true); });

  $("tameshi-test").addEventListener("submit", function (e) {
    e.preventDefault();
    call("/api/test-login", { id: $("tameshi-id").value, password: $("tameshi-password").value })
      .then(function (d) { keep(d.token); return signedIn(); })
      .catch(function (err) { note("tameshi-in-note", err.message, true); });
  });
  $("tameshi-out").addEventListener("click", function () {
    call("/api/logout", {}).catch(function () {}).then(signedOut);
  });

  // The dialogue with the guide
  function bubble(role, text) {
    var d = document.createElement("div");
    d.className = "msg " + (role === "user" ? "you" : "ai");
    d.textContent = text;
    $("tameshi-log").appendChild(d);
    d.scrollIntoView({ block: "nearest" });
  }
  $("tameshi-guide").addEventListener("change", function () {
    dialogue = [];
    $("tameshi-log").innerHTML = "";
  });
  $("tameshi-chat").addEventListener("submit", function (e) {
    e.preventDefault();
    var box = $("tameshi-say"), text = box.value.trim();
    if (!text) return;
    dialogue.push({ role: "user", text: text });
    bubble("user", text);
    box.value = "";
    note("tameshi-chat-note", "Gemini が答えています");
    var guide = $("tameshi-guide").value;
    call("/api/chat", { guide: guide, messages: dialogue }).then(function (d) {
      dialogue.push({ role: "model", text: d.text });
      bubble("model", d.text);
      note("tameshi-chat-note", "");
      left(d);
      if (window.kaiseki) kaiseki.event("tameshi", { value: "chat " + guide });
    }).catch(function (err) {
      dialogue.pop();
      note("tameshi-chat-note", err.message, true);
    });
  });

  // Today's news from the person's tastes
  $("tameshi-news").addEventListener("submit", function (e) {
    e.preventDefault();
    note("tameshi-news-note", "Gemini が Google 検索で探して、書いています(1 分ほどかかります)");
    $("tameshi-news-out").hidden = true;
    call("/api/news", { tastes: $("tameshi-tastes").value }).then(function (d) {
      $("tameshi-news-text").textContent = d.adoc;
      $("tameshi-news-out").hidden = false;
      note("tameshi-news-note", "");
      left(d);
      if (window.kaiseki) kaiseki.event("tameshi", { value: "news" });
    }).catch(function (err) { note("tameshi-news-note", err.message, true); });
  });
  $("tameshi-copy").addEventListener("click", function () {
    navigator.clipboard.writeText($("tameshi-news-text").textContent).then(function () {
      note("tameshi-news-note", "写しました");
    });
  });
})();

// The longer jobs: the apps there are now (#chousa), their problems (#kadai), and the
// design and manual from materials (#sekkei). Each section has its form and its own list of jobs.
(function () {
  var API = "/tameshi", KEY = "aiai.tameshi.token";
  var forms = document.querySelectorAll("form.tameshi-form");
  if (!forms.length) return;
  var timer = null;
  var NAMES = { sekkei: "設計書とマニュアル", chousa: "今あるアプリを探す", kadai: "今あるアプリの課題を集める" };
  // What a form needs before it is sent, in the words of the server's refusal
  var ENOUGH = {
    chousa: "何度も頼んでいることを書くか、資料を選んでください",
    kadai: "読ませる結果を選ぶか、資料を選んでください",
    sekkei: "SKILL.md と参考の資料を選ぶか、見本で試してください"
  };
  var STATUS = { waiting: "待っています", running: "進めています", done: "できました", error: "止まりました" };
  function token() { try { return sessionStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  function auth() { return { Authorization: "Bearer " + token() }; }
  function get(path) {
    return fetch(API + path, { headers: auth() }).then(function (r) {
      if (!r.ok) throw new Error("うまくいきませんでした(" + r.status + ")");
      return r;
    });
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function part(kind, sel) {
    var place = document.getElementById(kind);
    return place && place.querySelector(sel);
  }
  function note(kind, text, bad) {
    var n = part(kind, ".tameshi-job-note");
    n.textContent = text || "";
    n.classList.toggle("bad", !!bad);
  }

  forms.forEach(function (form) {
    var kind = form.dataset.kind, mihon = "";
    form.querySelectorAll("button[type=submit]").forEach(function (b) {
      b.addEventListener("click", function () { mihon = b.dataset.mihon || ""; });
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fields = form.elements, files = fields.files.files;
      var given = files.length || mihon || (kind === "chousa" && fields.note.value.trim()) || (kind === "kadai" && fields.research.value);
      if (!given) return note(kind, ENOUGH[kind], true);
      var data = new FormData(form);  // the fields this form has: research, name, kadai, note and files
      if (!files.length) data.delete("files");  // a file field with no file is sent as an empty part, which the server refuses
      data.append("kind", kind);
      if (mihon) data.append("mihon", "1");
      note(kind, "送っています");
      fetch(API + "/api/jobs", { method: "POST", headers: auth(), body: data }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok) throw new Error(Array.isArray(d.detail) ? d.detail.join("、") : (d.detail || "うまくいきませんでした"));
          return d;
        });
      }).then(function () {
        note(kind, "始めました。下で進み具合を見られます");
        if (window.kaiseki) kaiseki.event("tameshi", { value: kind });
        list();
      }).catch(function (err) { note(kind, err.message, true); });
    });
  });

  function list() {
    if (!token()) return;
    get("/api/jobs").then(function (r) { return r.json(); }).then(function (d) {
      document.querySelectorAll(".tameshi-jobs").forEach(function (b) { b.innerHTML = ""; });
      var busy = false;
      d.jobs.forEach(function (j) {
        var box = part(j.kind, ".tameshi-jobs");
        if (!box) return;
        busy = busy || j.status === "waiting" || j.status === "running";
        var item = el("div", "tameshi-job");
        item.appendChild(el("p", "", NAMES[j.kind] + " ・ " + j.created + " ・ " + STATUS[j.status]));
        item.appendChild(el("div", "tameshi-job-body"));
        box.appendChild(item);
        show(j.id, item.lastChild);
      });
      researches(d.jobs);
      clearTimeout(timer);
      if (busy) timer = setTimeout(list, 5000);
    }).catch(function () {});
  }
  function show(id, body) {
    get("/api/jobs/" + id).then(function (r) { return r.json(); }).then(function (j) {
      var ol = el("ol", "tameshi-steps");
      j.steps.forEach(function (s) { ol.appendChild(el("li", "", s.name + (s.seconds !== undefined ? "(" + s.seconds + " 秒)" : ""))); });
      body.appendChild(ol);
      if (j.error) body.appendChild(el("p", "fine bad", j.error));
      if (j.status !== "done") return;
      var zip = el("button", "button", "まとめてダウンロード(ZIP)");
      zip.type = "button";
      zip.addEventListener("click", function () {
        get("/api/jobs/" + id + "/zip").then(function (r) { return r.blob(); }).then(function (b) {
          var a = el("a");
          a.href = URL.createObjectURL(b);
          a.download = "aiai-" + j.kind + ".zip";
          a.click();
        });
      });
      body.appendChild(zip);
      if (j.kind === "chousa") {
        var go = el("button", "button", "この結果で、どう良くするかを考える");
        go.type = "button";
        go.addEventListener("click", function () {
          kaizenReset();
          $k("kaizen-job").value = id;
          $k("kaizen").scrollIntoView({ block: "start", behavior: "instant" });
          $k("kaizen-fuman").focus({ preventScroll: true });
        });
        body.appendChild(go);
        var gather = el("button", "button", "この結果で、課題を集める");
        gather.type = "button";
        gather.addEventListener("click", function () {
          part("kadai", "select[name=research]").value = id;
          jump("kadai", "input[name=name]");
        });
        body.appendChild(gather);
      }
      if (j.kind === "kadai") {
        var make = el("button", "button", "この資料で、設計書とマニュアルを作る");
        make.type = "button";
        make.addEventListener("click", function () {
          part("sekkei", "select[name=kadai]").value = id;
          jump("sekkei");
        });
        body.appendChild(make);
      }
      var pics = el("div", "tameshi-pics");
      j.files.forEach(function (path) {
        if (/\.png$/.test(path)) {
          get("/api/jobs/" + id + "/file?path=" + encodeURIComponent(path)).then(function (r) { return r.blob(); }).then(function (b) {
            var img = el("img");
            img.src = URL.createObjectURL(b);
            img.alt = path;
            pics.appendChild(img);
          });
        } else {
          var d = el("details"), s = el("summary", "", path), pre = el("pre");
          d.appendChild(s);
          d.appendChild(pre);
          d.addEventListener("toggle", function () {
            if (d.open && !pre.textContent) {
              get("/api/jobs/" + id + "/file?path=" + encodeURIComponent(path))
                .then(function (r) { return r.text(); }).then(function (t) { pre.textContent = t; });
            }
          });
          body.appendChild(d);
        }
      });
      body.appendChild(pics);
    }).catch(function () {});
  }
  // Step 3: how the apps there are could be better. The dialogue starts from the
  // person's own complaint, which app, when, and what goes wrong, and may read
  // what one of their searches found.
  var $k = function (id) { return document.getElementById(id); };
  var talk = [];
  // The selects that read a finished job are made again with every list, keeping the choice
  function pick(sel, kind, jobs) {
    if (!sel) return;
    var keep = sel.value, found = false;
    sel.length = 1;
    jobs.forEach(function (j) {
      if (j.kind !== kind || j.status !== "done") return;
      sel.add(new Option(NAMES[kind] + " ・ " + j.created, j.id));
      found = found || j.id === keep;
    });
    sel.value = found ? keep : "";
  }
  function researches(jobs) {
    pick($k("kaizen-job"), "chousa", jobs);                   // step 3 reads a search
    pick(part("kadai", "select[name=research]"), "chousa", jobs);  // step 5 reads a search
    pick(part("sekkei", "select[name=kadai]"), "kadai", jobs);     // step 6 reads the problems gathered
  }
  // Go to the head of a section, which stops below the bar above, and into its first field
  function jump(place, first) {
    document.getElementById(place).scrollIntoView({ block: "start", behavior: "instant" });
    var box = first && part(place, first);
    if (box) box.focus({ preventScroll: true });
  }
  function kaizenNote(text, bad) {
    $k("kaizen-note").textContent = text || "";
    $k("kaizen-note").classList.toggle("bad", !!bad);
  }
  function kaizenBubble(role, text) {
    var d = el("div", "msg " + (role === "user" ? "you" : "ai"), text);
    $k("kaizen-log").appendChild(d);
    d.scrollIntoView({ block: "nearest" });
  }
  function kaizenReset() {
    talk = [];
    $k("kaizen-log").innerHTML = "";
    $k("kaizen-talk").hidden = true;
    $k("kaizen-start").hidden = false;
    kaizenNote("");
  }
  function kaizenSend(text) {
    talk.push({ role: "user", text: text });
    kaizenBubble("user", text);
    kaizenNote("Gemini が考えています");
    fetch(API + "/api/kaizen", {
      method: "POST",
      headers: { Authorization: "Bearer " + token(), "Content-Type": "application/json" },
      body: JSON.stringify({ job: $k("kaizen-job").value, messages: talk })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(Array.isArray(d.detail) ? d.detail.join("、") : (d.detail || "うまくいきませんでした"));
        return d;
      });
    }).then(function (d) {
      talk.push({ role: "model", text: d.text });
      kaizenBubble("model", d.text);
      kaizenNote("");
      if (d.left !== undefined) $k("tameshi-left").textContent = "今日あと " + d.left + " 回";
      if (window.kaiseki) kaiseki.event("tameshi", { value: "kaizen" });
    }).catch(function (err) {
      talk.pop();
      $k("kaizen-log").removeChild($k("kaizen-log").lastChild);
      kaizenNote(err.message, true);
      if (!talk.length) { $k("kaizen-talk").hidden = true; $k("kaizen-start").hidden = false; }
    });
  }
  if ($k("kaizen-start")) {
    $k("kaizen-start").addEventListener("submit", function (e) {
      e.preventDefault();
      var fuman = $k("kaizen-fuman").value.trim();
      if (!fuman) return kaizenNote("困った場面と、困ったことを書いてください", true);
      var app = $k("kaizen-app").value.trim(), hoshii = $k("kaizen-hoshii").value.trim();
      $k("kaizen-start").hidden = true;
      $k("kaizen-talk").hidden = false;
      kaizenSend("使ったアプリ: " + (app || "(書いていません)") + "\n困った場面と、困ったこと: " + fuman
        + "\nどうなればよいか: " + (hoshii || "まだ分かりません"));
    });
    $k("kaizen-chat").addEventListener("submit", function (e) {
      e.preventDefault();
      var text = $k("kaizen-say").value.trim();
      if (!text) return;
      $k("kaizen-say").value = "";
      kaizenSend(text);
    });
    $k("kaizen-again").addEventListener("click", kaizenReset);
    $k("kaizen-job").addEventListener("change", function () { if (talk.length) kaizenReset(); });
  }

  // the list shows once signed in; the page's own script signs in first
  var tries = 0;
  (function wait() {
    if (!document.getElementById("tameshi-use").hidden) return list();
    if (++tries < 40) setTimeout(wait, 500);
  })();
})();
