// SPDX-License-Identifier: AGPL-3.0-or-later
// aiai's own events for kaiseki, so the record says where people read and what
// they look for: the section headings they reach, the folded full texts they
// open, the guides they copy or download for their AI, the links they follow,
// and the pages that were not found. Load after kaiseki.js, both with defer.
(function () {
  var k = window.kaiseki;
  if (!k) return;
  function ev(name, value) { k.event(name, { value: String(value || "").slice(0, 100) }); }

  if (document.querySelector("[data-notfound]")) ev("notfound", location.pathname);

  // A heading counts once a page, when it comes into view
  var heads = document.querySelectorAll("main h2, section[id]");
  if ("IntersectionObserver" in window) {
    var seen = new IntersectionObserver(function (items) {
      items.forEach(function (it) {
        if (!it.isIntersecting) return;
        var el = it.target;
        seen.unobserve(el);
        var h = el.tagName === "SECTION" ? el.querySelector("h2") : el;
        ev("section", el.id ? "#" + el.id + " " + (h ? h.textContent.trim() : "") : el.textContent.trim());
      });
    }, { rootMargin: "0px 0px -30% 0px" });
    heads.forEach(function (el) { seen.observe(el); });
  }

  document.addEventListener("toggle", function (e) {
    var d = e.target;
    if (d.tagName === "DETAILS" && d.open) {
      var s = d.querySelector("summary");
      ev("open", s ? s.textContent.trim() : "");
    }
  }, true);

  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-copy], a[download]");
    if (b) return ev("use", b.hasAttribute("download") ? "zip" : "copy");
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    var url;
    try { url = new URL(a.href, location.href); } catch (err) { return; }
    if (url.host !== location.host) ev("out", url.host + url.pathname);
    else if (url.pathname !== location.pathname) ev("link", url.pathname + url.hash);
  }, true);
})();
