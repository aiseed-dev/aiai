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
  }
  function note(id, text, bad) {
    var el = $(id);
    el.textContent = text || "";
    el.classList.toggle("bad", !!bad);
  }
  function left(d) {
    if (d && d.left !== undefined) $("tameshi-left").textContent = "今日あと " + d.left + " 回";
  }

  function signedIn() {
    return call("/api/me").then(function (me) {
      $("tameshi-in").hidden = true;
      $("tameshi-use").hidden = false;
      $("tameshi-who").textContent = me.provider === "test" ? "テストアカウント" : (me.email || me.provider);
      $("tameshi-left").textContent = "今日あと: 対話 " + me.left.chat + " 回、ニュース " + me.left.news + " 回";
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
