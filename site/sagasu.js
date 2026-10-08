// SPDX-License-Identifier: AGPL-3.0-or-later
// The site search on /sagasu.html. The words are looked up in the pages'
// index (/sagasu.json, made by make_site.py), and the server's AI (POST
// /api/sagasu) picks the pages that fit even when the words differ. The AI
// only picks pages; it writes no answer. Each search goes into the record
// (kaiseki), and one that finds nothing is marked, as a page to write.
(function () {
  var form = document.getElementById("sagasu");
  if (!form) return;
  var input = form.querySelector("input"), out = document.getElementById("sagasu-out");
  var index = fetch("/sagasu.json").then(function (r) { return r.json(); });

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function item(e) {
    return '<li><a href="' + esc(e.u) + '"><strong>' + esc(e.t) + "</strong>" +
      (e.h ? '<span class="sagasu-h">' + esc(e.h) + "</span>" : "") + "</a>" +
      (e.x ? '<p class="sagasu-x">' + esc(e.x) + "</p>" : "") + "</li>";
  }
  function words(q, all) {
    var ws = q.toLowerCase().split(/\s+/).filter(Boolean);
    return all.filter(function (e) {
      var text = (e.t + " " + e.h + " " + e.x).toLowerCase();
      return ws.every(function (w) { return text.indexOf(w) >= 0; });
    }).slice(0, 10);
  }
  function show(q, mine, ai, waiting) {
    var html = "";
    if (ai && ai.length) html += '<h2>AI が選んだページ</h2><ol class="sagasu-list">' + ai.map(item).join("") + "</ol>";
    if (mine.length) html += '<h2>言葉が入っているページ</h2><ol class="sagasu-list">' + mine.map(item).join("") + "</ol>";
    if (waiting) html += '<p class="fine">AI が合うページを選んでいます。</p>';
    else if (!html) html = "<p>「" + esc(q) + "」に合うページは、まだありません。探した言葉は記録して、足りないページを作るときに使います。</p>";
    out.innerHTML = html;
  }

  function search(q) {
    q = q.trim().slice(0, 100);
    if (!q) return;
    index.then(function (all) {
      var mine = words(q, all);
      show(q, mine, null, true);
      var ask = fetch("/api/sagasu", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q: q }),
      }).then(function (r) { return r.ok ? r.json() : { hits: [] }; }).catch(function () { return { hits: [] }; });
      ask.then(function (res) {
        var ai = (res.hits || []).map(function (i) { return all[i]; }).filter(Boolean);
        var mineOnly = mine.filter(function (e) { return ai.indexOf(e) < 0; });
        show(q, mineOnly, ai, false);
        if (window.kaiseki) {
          kaiseki.event("search", { value: q });
          if (!ai.length && !mine.length) kaiseki.event("nohit", { value: q });
        }
      });
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    search(input.value);
  });
})();
