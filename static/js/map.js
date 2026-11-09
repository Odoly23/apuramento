/* Peta Timor-Leste (Highcharts Map Collection GeoJSON, koordenada planar) -> SVG tanpa dependensi. */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var geoCache = null;

  function load(url) {
    if (geoCache) return geoCache;
    geoCache = fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json(); });
    return geoCache;
  }
  function path(geom, ymax) {
    var polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates, d = [];
    polys.forEach(function (poly) {
      poly.forEach(function (ring) {
        d.push("M" + ring.map(function (p) { return p[0] + "," + (ymax - p[1]); }).join("L") + "Z");
      });
    });
    return d.join("");
  }

  function TLMap(container, geoUrl, onHover) {
    var self = this;
    this.box = container; this.paths = {}; this.onHover = onHover; this.ready = false; this.pending = null;
    load(geoUrl).then(function (geo) {
      var xs = [], ys = [];
      (function walk(c) { if (typeof c[0] === "number") { xs.push(c[0]); ys.push(c[1]); } else c.forEach(walk); })(geo.features.map(function (f) { return f.geometry.coordinates; }));
      var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
      var svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", (x0 - 100) + " -100 " + (x1 - x0 + 200) + " " + (y1 - y0 + 200));
      svg.setAttribute("role", "img"); svg.style.width = "100%"; svg.style.height = "auto"; svg.style.display = "block";
      geo.features.forEach(function (f) {
        var p = document.createElementNS(NS, "path");
        p.setAttribute("d", path(f.geometry, y1));
        p.setAttribute("class", "tl-region");
        p.setAttribute("vector-effect", "non-scaling-stroke");
        var key = f.properties["hc-key"];
        p.dataset.key = key; self.paths[key] = p;
        p.addEventListener("mouseenter", function () { self.onHover && self.onHover(key, p); });
        p.addEventListener("focus", function () { self.onHover && self.onHover(key, p); });
        p.setAttribute("tabindex", "0");
        svg.appendChild(p);
      });
      container.innerHTML = ""; container.appendChild(svg);
      self.ready = true;
      if (self.pending) self.paint.apply(self, self.pending);
    }).catch(function () { container.textContent = "⚠ map"; });
  }
  // colorFn(hckey) -> {fill, opacity, title} ka null
  TLMap.prototype.paint = function (colorFn) {
    if (!this.ready) { this.pending = [colorFn]; return; }
    for (var k in this.paths) {
      var c = colorFn(k), p = this.paths[k];
      if (c) { p.style.fill = c.fill; p.style.opacity = c.opacity; }
      else { p.style.fill = "var(--bg2)"; p.style.opacity = 1; }
    }
  };
  window.TLMap = TLMap;
})();
