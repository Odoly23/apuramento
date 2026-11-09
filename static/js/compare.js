(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var T = AP.T, esc = AP.esc, fmt = AP.fmt;
  var snap = JSON.parse($("#snap").textContent);
  var cs = snap.contestants, cmap = AP.contestantMap(cs);
  var state = { level: "municipality", parent: "", nodes: snap.municipalities, munis: snap.municipalities, a: null, b: null, sort: "name", dir: 1 };
  var eid = snap.election.id;

  function col(c) { return /^#[0-9a-f]{6}$/i.test(c.color) ? c.color : "#64748b"; }
  cs.forEach(function (c, i) { c._i = i; });
  function fillSel(sel, val) {
    sel.innerHTML = cs.map(function (c) { return '<option value="' + c.id + '">' + esc(c.short + " · " + c.name) + "</option>"; }).join("");
    sel.value = val;
  }
  var ca = $("#ca"), cb = $("#cb");
  var rk = cs.slice().sort(function (a, b) { return (snap.national.votes[b.id] || 0) - (snap.national.votes[a.id] || 0); });
  state.a = rk[0] ? rk[0].id : cs[0].id; state.b = rk[1] ? rk[1].id : cs[0].id;
  fillSel(ca, state.a); fillSel(cb, state.b);
  ca.onchange = function () { state.a = +ca.value; draw(); };
  cb.onchange = function () { state.b = +cb.value; draw(); };

  function load() {
    var url = "/api/live/?e=" + eid + "&level=" + state.level + (state.parent ? "&parent=" + state.parent : "");
    return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
      state.nodes = d.nodes; state.munis = d.municipalities; draw();
    });
  }

  var seg = $("#levelSeg"), ps = $("#parentSel");
  seg.addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    state.level = b.dataset.level; state.parent = "";
    [].forEach.call(seg.children, function (x) { x.classList.toggle("on", x === b); });
    ps.classList.toggle("hide", state.level === "municipality");
    if (state.level !== "municipality") {
      ps.innerHTML = '<option value="">' + esc(T.all) + "</option>" + snap.municipalities.map(function (m) { return '<option value="' + m.id + '">' + esc(m.name) + "</option>"; }).join("");
    }
    load();
  });
  ps.onchange = function () { state.parent = ps.value; load(); };
  // suku/postu parent = munisípiu ba postu; ba suku, parent postu -> filtru simples: la iha munisípiu iha suku, uza postu
  // (parent param ba level suku refere ba postu; hodi simplifika, pilih munisípiu hodi filtra postu deit)

  function draw() {
    var nodes = state.nodes.slice();
    // head-to-head
    var A = cmap[state.a], B = cmap[state.b];
    var rows = nodes.filter(function (n) { return n.valid > 0; });
    rows.sort(function (x, y) { return ((y.shares[state.a] || 0) - (y.shares[state.b] || 0)) - ((x.shares[state.a] || 0) - (x.shares[state.b] || 0)); });
    $("#h2h").innerHTML = rows.slice(0, 14).map(function (n) {
      var d = (n.shares[state.a] || 0) - (n.shares[state.b] || 0), w = Math.min(50, Math.abs(d) / 2);
      return '<div><div style="display:flex;justify-content:space-between"><b>' + esc(n.name) + '</b><span style="color:' + (d >= 0 ? col(A) : col(B)) + ';font-weight:800">' +
        (d >= 0 ? esc(A.short) : esc(B.short)) + " +" + Math.abs(d).toFixed(1) + '</span></div><div class="res-track" style="position:relative">' +
        '<div style="position:absolute;left:50%;top:0;bottom:0;width:2px;background:var(--line)"></div>' +
        '<i style="position:absolute;height:100%;' + (d >= 0 ? "left:50%" : "right:50%") + ";width:" + w + "%;background:" + (d >= 0 ? col(A) : col(B)) + '"></i></div></div>';
    }).join("") || '<div class="muted">' + T.no_data + "</div>";

    // lider kontagem
    var count = {};
    nodes.forEach(function (n) { if (n.leader) count[n.leader] = (count[n.leader] || 0) + 1; });
    var tot = nodes.length || 1;
    $("#leaders").innerHTML = '<div class="stack" style="height:22px;margin-bottom:14px">' + Object.keys(count).map(function (k) {
      return '<i style="width:' + (100 * count[k] / tot) + "%;background:" + col(cmap[k]) + '" title="' + esc(cmap[k].short) + '"></i>';
    }).join("") + "</div>" + Object.keys(count).sort(function (a, b) { return count[b] - count[a]; }).map(function (k) {
      return '<div style="display:flex;justify-content:space-between;padding:6px 0"><span class="chip" style="background:' + col(cmap[k]) + '">' + esc(cmap[k].short) + "</span><b>" + count[k] + " / " + nodes.length + "</b></div>";
    }).join("") || '<div class="muted">' + T.no_data + "</div>";

    // tabela
    var sortKey = state.sort;
    nodes.sort(function (x, y) {
      var vx = sortKey === "name" ? x.name : sortKey === "turnout" ? x.turnout : sortKey === "progress" ? x.progress : sortKey === "margin" ? x.margin : (x.shares[sortKey] || 0);
      var vy = sortKey === "name" ? y.name : sortKey === "turnout" ? y.turnout : sortKey === "progress" ? y.progress : sortKey === "margin" ? y.margin : (y.shares[sortKey] || 0);
      return (vx > vy ? 1 : vx < vy ? -1 : 0) * state.dir;
    });
    var head = "<tr><th data-k=\"name\">" + esc(T.region) + '</th><th class="num" data-k="progress">' + esc(T.progress) + '</th><th class="num" data-k="turnout">' + esc(T.turnout) + "</th>" +
      cs.map(function (c) { return '<th class="num" data-k="' + c.id + '"><span class="chip" style="background:' + col(c) + '">' + esc(c.short) + "</span></th>"; }).join("") +
      "<th>" + esc(T.share) + '</th><th class="num" data-k="margin">' + esc(T.margin) + "</th></tr>";
    var body = nodes.map(function (n) {
      var cells = cs.map(function (c) {
        var s = n.shares[c.id] || 0, win = n.leader === c.id;
        return '<td class="num leadcell" style="' + (win ? "color:" + col(c) + ";" : "") + '">' + (n.valid ? s.toFixed(1) + "%" : "–") + "</td>";
      }).join("");
      var stack = '<div class="stack">' + cs.map(function (c) { return '<i style="width:' + (n.shares[c.id] || 0) + "%;background:" + col(c) + '"></i>'; }).join("") + "</div>";
      return "<tr><td><b>" + esc(n.name) + '</b></td><td class="num">' + n.progress + '%</td><td class="num">' + n.turnout + "%</td>" + cells + "<td>" + stack + '</td><td class="num">' + fmt(n.margin) + "</td></tr>";
    }).join("");
    $("#tbl").innerHTML = head + body;
    $("#tbl").querySelectorAll("th[data-k]").forEach(function (th) {
      th.style.cursor = "pointer";
      th.onclick = function () {
        var k = th.dataset.k; state.dir = state.sort === k ? -state.dir : -1; state.sort = k; draw();
      };
    });
  }
  draw();
  AP.poll("/api/live/?e=" + eid + "&level=" + state.level, function () { load(); }, 15000);
})();
