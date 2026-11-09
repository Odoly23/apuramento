(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var AP = (window.AP = {});
  AP.T = JSON.parse(($("#i18n") || {}).textContent || "{}");
  AP.csrf = ($('meta[name="csrf"]') || {}).content || "";
  AP.fmt = function (n) { return Math.round(n || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); };
  AP.esc = function (s) {
    var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML;
  };
  AP.el = function (html) { var t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };
  AP.contrast = function () { return "#fff"; };

  // tema
  var tb = $("#themeBtn");
  if (tb) tb.addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", cur);
    try { localStorage.setItem("theme", cur); } catch (e) {}
  });
  var mb = $("#menuBtn");
  if (mb) mb.addEventListener("click", function () { $("#side").classList.toggle("open"); });
  document.querySelectorAll("[data-autosubmit]").forEach(function (s) {
    s.addEventListener("change", function () { s.form.submit(); });
  });

  // chat
  var chat = $("#chat"), log = $("#chatLog"), input = $("#chatInput");
  function say(text, who) {
    var b = AP.el('<div class="bub ' + who + '"></div>'); b.textContent = text; log.appendChild(b);
    log.scrollTop = log.scrollHeight; return b;
  }
  var sugg = ["?", "lidera?", "partisipasaun", "progresu", "konflitu", "seguransa", "oinsá hatama dadus?"];
  var suggBox = $("#chatSugg");
  var langSugg = {
    tet: ["Sé lidera?", "Partisipasaun", "Progresu", "Seguransa", "Oinsá hatama dadus?"],
    pt: ["Quem lidera?", "Participação", "Progresso", "Segurança", "Como introduzir dados?"],
    en: ["Who leads?", "Turnout", "Progress", "Security", "How to enter data?"],
    id: ["Siapa unggul?", "Partisipasi", "Kemajuan", "Keamanan", "Cara input data?"]
  }[document.documentElement.lang] || sugg;
  function ask(q) {
    if (!q) return;
    say(q, "me");
    var wait = say("…", "bot");
    fetch("/api/chat/", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": AP.csrf },
      body: JSON.stringify({ q: q })
    }).then(function (r) { return r.json(); })
      .then(function (j) { wait.textContent = j.a; })
      .catch(function () { wait.textContent = "⚠"; });
  }
  if (chat) {
    langSugg.forEach(function (s) {
      var b = AP.el('<button type="button"></button>'); b.textContent = s;
      b.addEventListener("click", function () { ask(s); }); suggBox.appendChild(b);
    });
    var greeted = false;
    $("#chatFab").addEventListener("click", function () {
      chat.classList.toggle("open");
      if (!greeted) { say(AP.T.chat_hello, "bot"); greeted = true; }
      input.focus();
    });
    $("#chatClose").addEventListener("click", function () { chat.classList.remove("open"); });
    $("#chatForm").addEventListener("submit", function (e) {
      e.preventDefault(); var q = input.value.trim(); input.value = ""; ask(q);
    });
  }

  // helpers hodi render rezultadu
  AP.contestantMap = function (list) {
    var m = {}; list.forEach(function (c) { m[c.id] = c; }); return m;
  };
  AP.timeago = function (iso) {
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return Math.round(s) + "s";
    if (s < 3600) return Math.round(s / 60) + "m";
    if (s < 86400) return Math.round(s / 3600) + "h";
    return Math.round(s / 86400) + "d";
  };
  AP.poll = function (url, cb, ms) {
    function tick() {
      fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(cb)
        .catch(function () {}).finally(function () { setTimeout(tick, ms || 10000); });
    }
    setTimeout(tick, ms || 10000);
  };
})();
