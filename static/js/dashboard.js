(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var T = AP.T, esc = AP.esc, fmt = AP.fmt;
  var data = JSON.parse($("#snap").textContent);
  var myParty = JSON.parse($("#myParty").textContent);
  var electionId = data.election.id;

  function col(c) { return /^#[0-9a-f]{6}$/i.test(c.color) ? c.color : "#64748b"; }
  function pct(n, d) { return d ? (100 * n / d) : 0; }

  function kpi(label, value, sub, bar) {
    return '<div class="card kpi"><div class="label">' + esc(label) + '</div><div class="value">' + value +
      '</div><div class="sub">' + sub + '</div>' + (bar != null ? '<div class="bar" style="margin-top:8px"><i style="width:' + bar + '%"></i></div>' : "") + "</div>";
  }

  function render(d) {
    var n = d.national, cs = d.contestants, st = d.states || {};
    $("#kpis").innerHTML =
      kpi(T.centres_reporting, fmt(n.centres_reporting) + " / " + fmt(n.centres_total), n.progress + "%", n.progress) +
      kpi(T.turnout, n.turnout + "%", fmt(n.voted) + " " + T.voted.toLowerCase()) +
      kpi(T.total_votes, fmt(n.valid), T.blank + " " + fmt(n.blank) + " · " + T.invalid + " " + fmt(n.invalid)) +
      kpi(T.conflicts, '<span style="color:' + (n.conflicts ? "var(--bad)" : "var(--ok)") + '">' + fmt(n.conflicts) + "</span>", T.verification);

    // rezultadu
    var ranked = cs.slice().sort(function (a, b) { return (n.votes[b.id] || 0) - (n.votes[a.id] || 0); });
    var max = Math.max.apply(null, ranked.map(function (c) { return n.shares[c.id] || 0; }).concat([1]));
    $("#results").innerHTML = ranked.map(function (c, i) {
      var s = n.shares[c.id] || 0, v = n.votes[c.id] || 0;
      return '<div class="res-row' + (myParty && c.party_id === myParty ? " mine" : "") + '">' +
        '<div class="badge-n" style="background:' + col(c) + '">#' + c.number + "</div>" +
        '<div><div class="res-name">' + (i === 0 && v ? "🏆 " : "") + esc(c.name) + ' <span class="muted small">' + esc(c.short) +
        (myParty && c.party_id === myParty ? " · " + esc(T.your_party) : "") + "</span></div>" +
        '<div class="res-track"><i style="width:' + (100 * s / max) + "%;background:" + col(c) + '"></i></div></div>' +
        '<div class="res-val"><b>' + s.toFixed(2) + "%</b><div class=\"muted small\">" + fmt(v) + " " + T.votes + "</div></div></div>";
    }).join("");

    // donut
    var acc = 0, stops = [];
    ranked.forEach(function (c) {
      var s = n.shares[c.id] || 0; if (!s) return;
      stops.push(col(c) + " " + acc + "% " + (acc + s) + "%"); acc += s;
    });
    $("#donut").style.background = stops.length ? "conic-gradient(" + stops.join(",") + ")" : "var(--bg2)";
    $("#donutTotal").textContent = fmt(n.valid);
    $("#legend").innerHTML = ranked.map(function (c) {
      return '<span><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:' + col(c) + '"></i> ' + esc(c.short) + "</span>";
    }).join("");

    // estadu
    var names = { verified: T.verified, consensus: T.consensus, provisional: T.provisional, conflict: T.conflict, missing: T.not_submitted };
    var tot = n.centres_total || 1;
    $("#states").innerHTML = Object.keys(names).map(function (k) {
      var v = st[k] || 0;
      return '<div style="margin-bottom:10px"><div style="display:flex;justify-content:space-between"><span>' + esc(names[k]) +
        "</span><b>" + fmt(v) + '</b></div><div class="bar"><i style="width:' + pct(v, tot) + '%"></i></div></div>';
    }).join("");

    var cmap = AP.contestantMap(cs);
    drawMap(d, cmap);

    // tiles
    function tile(m, pre) {
      if (!m.leader) return '<div class="tile empty"><b>' + pre + esc(m.name) + '</b><span class="small">' + T.no_data + "</span></div>";
      var c = cmap[m.leader], s = m.shares[m.leader] || 0, alpha = Math.min(1, 0.55 + s / 120);
      return '<div class="tile" style="background:linear-gradient(135deg,' + col(c) + "," + col(c) + 'cc);opacity:' + alpha + '" title="' + esc(m.name) + '">' +
        "<b>" + pre + esc(m.name) + '</b><div><div class="pc">' + s.toFixed(1) + "%</div><span class=\"small\">" + esc(c.short) + " · " + m.progress + '%</span></div><div class="pr" style="width:' + m.progress + '%"></div></div>';
    }
    $("#tiles").innerHTML = d.municipalities.map(function (m) { return tile(m, ""); }).join("");
    $("#dtiles").innerHTML = (d.nasauns || []).map(function (m) { return tile(m, "🌍 "); }).join("") || '<span class="muted small">' + T.no_data + "</span>";

    // feed
    var stLabel = { pending: T.pending, verified: T.verified, rejected: T.rejected };
    $("#feed").innerHTML = (d.recent || []).map(function (r) {
      return "<div><span>📍</span><div style=\"flex:1\"><b>" + esc(r.centre) + '</b><div class="muted small">' + esc(r.muni) + " · " + esc(r.by) +
        '</div></div><span class="badge ' + (r.status === "verified" ? "ok" : r.status === "rejected" ? "bad" : "warn") + '">' +
        esc(stLabel[r.status] || r.status) + '</span><span class="muted small">' + AP.timeago(r.at) + "</span></div>";
    }).join("") || '<div class="muted">' + T.no_data + "</div>";
    $("#updated").textContent = T.updated + " " + new Date().toLocaleTimeString();
  }

  // ---- peta ----
  var tl = new TLMap($("#map"), $("#map").dataset.geo, function (key) { showInfo(key); });
  var metricSel = $("#metric"), metric = "leader", lastData = data, byKey = {};
  function buildMetricOptions(cs) {
    if (metricSel.options.length) return;
    var opts = [["leader", T.map_leader], ["turnout", T.map_turnout], ["progress", T.map_progress]]
      .concat(cs.map(function (c) { return [String(c.id), c.short + " · " + c.name]; }));
    metricSel.innerHTML = opts.map(function (o) { return '<option value="' + o[0] + '">' + esc(o[1]) + "</option>"; }).join("");
  }
  metricSel.addEventListener("change", function () { metric = metricSel.value; drawMap(lastData, AP.contestantMap(lastData.contestants)); });
  function showInfo(key) {
    var m = byKey[key], cs = lastData.contestants, cmap = AP.contestantMap(cs);
    if (!m) { $("#mapname").textContent = "—"; $("#mapinfo").textContent = T.no_data; return; }
    $("#mapname").textContent = m.name;
    var top = Object.keys(m.shares).sort(function (a, b) { return m.shares[b] - m.shares[a]; }).slice(0, 4);
    $("#mapinfo").innerHTML = '<div class="muted small">' + esc(T.centres_reporting) + ": <b>" + m.centres_reporting + "/" + m.centres_total + "</b> (" + m.progress + "%) · " + esc(T.turnout) + ": <b>" + m.turnout + "%</b></div>" +
      (top.length && m.valid ? top.map(function (k) { var c = cmap[k]; return '<div style="display:flex;justify-content:space-between;margin-top:4px"><span class="chip" style="background:' + col(c) + '">' + esc(c.short) + "</span><b>" + m.shares[k].toFixed(1) + "% <span class=\"muted small\">" + fmt(m.votes[k]) + "</span></b></div>"; }).join("") : "<div>" + T.no_data + "</div>");
  }
  function drawMap(d, cmap) {
    lastData = d; buildMetricOptions(d.contestants); byKey = {};
    d.municipalities.forEach(function (m) { if (m.hckey) byKey[m.hckey] = m; });
    var maxShare = 1;
    if (metric !== "leader" && metric !== "turnout" && metric !== "progress")
      d.municipalities.forEach(function (m) { maxShare = Math.max(maxShare, m.shares[metric] || 0); });
    tl.paint(function (key) {
      var m = byKey[key]; if (!m) return null;
      if (metric === "leader") { if (!m.leader) return null; var c = cmap[m.leader]; return { fill: col(c), opacity: Math.min(1, 0.5 + (m.shares[m.leader] || 0) / 80) }; }
      if (metric === "turnout") return m.voted ? { fill: "var(--accent)", opacity: 0.25 + 0.75 * Math.min(1, m.turnout / 100) } : null;
      if (metric === "progress") return { fill: "var(--ok)", opacity: 0.15 + 0.85 * Math.min(1, m.progress / 100) };
      var cc = cmap[metric]; var s = m.shares[metric] || 0;
      return m.valid ? { fill: col(cc), opacity: 0.15 + 0.85 * (s / maxShare) } : null;
    });
    var leg = $("#mapleg"), c2 = metric === "leader" ? null : cmap[metric];
    leg.innerHTML = metric === "leader" ? d.contestants.map(function (c) { return '<span><i style="display:inline-block;flex:0 0 10px;width:10px;height:10px;border-radius:3px;background:' + col(c) + '"></i> ' + esc(c.short) + "</span>"; }).join(" ")
      : '<span>0</span><i style="background:linear-gradient(90deg,transparent,' + (c2 ? col(c2) : metric === "progress" ? "var(--ok)" : "var(--accent)") + ');border:1px solid var(--line)"></i><span>' + (c2 ? maxShare.toFixed(0) + "%" : "100%") + "</span>";
  }

  render(data);
  AP.poll("/api/live/?e=" + electionId + "&level=municipality", function (d) { render(d); }, 10000);
})();
