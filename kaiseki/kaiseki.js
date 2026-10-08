// SPDX-License-Identifier: AGPL-3.0-or-later
// kaiseki: put on every page as
//   <script src="/kaiseki.js" data-to="https://analytics.aiseed.dev"
//           data-own="time-j.net aiseed.dev" defer></script>
// Sends about what Google Analytics collects: each view (page, title,
// referrer, utm_*, language, time zone, screen, browser, session), the time
// the page was in view when it is left, and events the page names with
// kaiseki.event("name"). A person who presses 受け入れる gets a random ID in
// this site's own cookie, and a visit ID in sessionStorage; they go with
// every record, and the cookie ID is carried to our other sites (data-own) in
// the #fragment of the links between them (a fragment is never sent to any
// server), so one person's visits read together. 受け入れない keeps no ID of
// any kind, and the views are only counted. kaiseki.forget() deletes the ID
// and everything kept under it. kaiseki.id() gives the ID to the site's own
// server, which links it to a signed-in member (POST /v1/link on its side).
// data-ask="no": no bar and no ID of any kind; views, leave and events are
// only counted. data-ask-text replaces the bar's question (why it records).
(function () {
  const me = document.currentScript;
  const TO = (me && me.dataset.to) || "https://analytics.aiseed.dev";
  const OWN = ((me && me.dataset.own) || "").split(/\s+/).filter(Boolean);
  const NOASK = !!me && me.dataset.ask === "no";
  const QUESTION = (me && me.dataset.askText) ||
    "このサイトをよくし、あなたに合った案内を出すために、見たページの記録を残してよいですか。";
  const NAME = "kaiseki_id";
  const CHOICE = "kaiseki_choice";
  const PARAM = "kaiseki_id";
  const YEAR = 400 * 24 * 3600;
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

  function cookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }
  function setCookie(name, value, maxAge) {
    document.cookie = name + "=" + encodeURIComponent(value) + "; Max-Age=" + maxAge + "; Path=/; SameSite=Lax; Secure";
  }
  function refHost() {
    try {
      const h = new URL(document.referrer).host;
      return h === location.host ? "" : h;
    } catch (e) {
      return "";
    }
  }
  function utm() {
    const q = new URLSearchParams(location.search);
    const v = ["source", "medium", "campaign", "term", "content"].map(function (k) { return q.get("utm_" + k) || ""; });
    return v.some(Boolean) ? v.join("|") : "";
  }
  function session() {
    let s = "";
    if (NOASK || cookie(CHOICE) !== "yes") return "";
    try {
      s = sessionStorage.getItem(NAME + "_s") || "";
      if (!UUID.test(s)) {
        s = crypto.randomUUID();
        sessionStorage.setItem(NAME + "_s", s);
      }
    } catch (e) {}
    return s;
  }
  function vidNow() {
    return NOASK ? "" : cookie(NAME);
  }
  function own(host) {
    return OWN.some(function (d) { return host === d || host.endsWith("." + d); });
  }

  // An ID carried here from another of our sites, by a link (#kaiseki_id=)
  (function adopt() {
    const url = new URL(location.href);
    const hash = new URLSearchParams(url.hash.slice(1));
    const vid = (hash.get(PARAM) || "").toLowerCase();
    if (!hash.has(PARAM)) return;
    hash.delete(PARAM);
    url.hash = hash.toString();
    history.replaceState(history.state, "", url.toString());
    if (!NOASK && UUID.test(vid) && cookie(CHOICE) !== "no") {
      setCookie(CHOICE, "yes", YEAR);
      setCookie(NAME, vid, YEAR);
    }
  })();

  function send(path, data) {
    const body = JSON.stringify(data);
    if (!(navigator.sendBeacon && navigator.sendBeacon(TO + path, body))) {
      fetch(TO + path, { method: "POST", body: body, keepalive: true, mode: "cors" }).catch(function () {});
    }
  }
  function record(event, extra) {
    const data = {
      site: location.host,
      path: location.pathname,
      event: event,
      title: document.title,
      referrer: refHost(),
      utm: utm(),
      lang: navigator.language || "",
      tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || ""),
      screen: screen.width + "x" + screen.height,
      ua: navigator.userAgent,
      sid: session(),
      vid: vidNow(),
    };
    send("/v1/hit", Object.assign(data, extra || {}));
  }

  // How far down the page was seen, 0 to 100
  let deepest = 0;
  function seen() {
    const el = document.documentElement;
    const h = el.scrollHeight;
    const p = h > 0 ? Math.round(Math.min(1, (window.scrollY + window.innerHeight) / h) * 100) : 100;
    if (p > deepest) deepest = p;
  }
  window.addEventListener("scroll", seen, { passive: true });
  seen();

  // Time the page was in view, sent when it is hidden or left
  let shown = document.visibilityState === "visible" ? Date.now() : 0;
  let total = 0;
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      if (shown) total += Date.now() - shown;
      shown = 0;
      if (total > 0) record("leave", { seconds: Math.round(total / 1000), scroll: deepest });
      total = 0;
    } else {
      shown = Date.now();
    }
  });

  // Carry the ID on links to our other sites
  document.addEventListener("click", function (e) {
    const a = e.target.closest && e.target.closest("a[href]");
    const vid = vidNow();
    if (!a || !vid) return;
    let url;
    try {
      url = new URL(a.href, location.href);
    } catch (err) {
      return;
    }
    if (url.host !== location.host && own(url.host)) {
      const hash = new URLSearchParams(url.hash.slice(1));
      hash.set(PARAM, vid);
      url.hash = hash.toString();
      a.href = url.toString();
    }
  }, true);

  function choose(yes) {
    if (NOASK) return;
    setCookie(CHOICE, yes ? "yes" : "no", YEAR);
    if (yes && !cookie(NAME)) setCookie(NAME, crypto.randomUUID(), YEAR);
    // The page in view counts from here, with the ID
    if (yes) record("accept");
    if (!yes && cookie(NAME)) forget();
    if (!yes) {
      try { sessionStorage.removeItem(NAME + "_s"); } catch (e) {}
    }
    const bar = document.getElementById("kaiseki-bar");
    if (bar) bar.remove();
  }
  function forget() {
    const vid = cookie(NAME);
    if (vid) send("/v1/forget", { vid: vid });
    setCookie(NAME, "", 0);
  }
  // Fixed to the bottom of the screen, so it is seen on long pages. :where() gives
  // these rules no weight, so any rule of the site for #kaiseki-bar wins.
  function style() {
    if (document.getElementById("kaiseki-style")) return;
    const st = document.createElement("style");
    st.id = "kaiseki-style";
    st.textContent =
      ":where(#kaiseki-bar){position:fixed;left:0;right:0;bottom:0;z-index:2147483647;padding:12px 16px;" +
      "background:#fff;color:#111;border-top:1px solid #ccc;box-shadow:0 -2px 8px rgba(0,0,0,.15);" +
      "font:14px/1.6 system-ui,sans-serif}" +
      "@media (prefers-color-scheme: dark){:where(#kaiseki-bar){background:#1e1e1e;color:#eee;border-top-color:#444}}";
    document.head.appendChild(st);
  }
  function ask() {
    const bar = document.createElement("div");
    bar.id = "kaiseki-bar";
    style();
    bar.innerHTML =
      "<p><span data-q></span>" +
      "受け入れると、このサイトの Cookie に番号を置き、その番号で記録をまとめます。" +
      ' <a href="/kaiseki/">くわしく</a></p>' +
      '<button type="button" data-yes>受け入れる</button> <button type="button" data-no>受け入れない</button>';
    bar.querySelector("[data-q]").textContent = QUESTION;
    bar.querySelector("[data-yes]").onclick = function () { choose(true); };
    bar.querySelector("[data-no]").onclick = function () { choose(false); };
    document.body.appendChild(bar);
  }

  window.kaiseki = {
    choose: choose,
    forget: forget,
    // A short value, such as a search word: kaiseki.event("search", { value: "..." })
    event: function (name, extra) {
      record(name, extra && extra.value != null ? { value: String(extra.value).slice(0, 100) } : {});
    },
    id: vidNow,
    to: TO,
  };
  record("view");
  if (!NOASK && !cookie(CHOICE)) ask();
})();
