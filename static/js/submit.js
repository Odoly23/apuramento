(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var T = AP.T;
  var reg = parseInt(($("#registered") || {}).dataset.n || "0", 10);
  var form = $("#reportForm"), box = $("#sumbox");
  function num(el) { var v = parseInt(el.value, 10); return isNaN(v) || v < 0 ? 0 : v; }
  function calc() {
    var sum = 0; document.querySelectorAll(".cvote").forEach(function (i) { sum += num(i); });
    var voted = num($("#voted"));
    $("#sumval").textContent = AP.fmt(sum); $("#votedval").textContent = AP.fmt(voted);
    var ok = voted > 0 && sum === voted && (!reg || voted <= reg);
    box.classList.toggle("ok", ok); box.classList.toggle("bad", !ok);
    $("#sumtxt").textContent = ok ? T.sum_ok : (reg && voted > reg ? T.err_registered.replace("%(n)s", AP.fmt(reg)) : T.sum_bad);
  }
  form.addEventListener("input", calc); calc();

  var photos = $("#id_photos"), prev = $("#preview");
  if (photos) photos.addEventListener("change", function () {
    prev.innerHTML = "";
    [].slice.call(photos.files, 0, 6).forEach(function (f) {
      if (!/^image\//.test(f.type)) return;
      var img = document.createElement("img"); img.alt = ""; img.src = URL.createObjectURL(f);
      img.onload = function () { URL.revokeObjectURL(img.src); }; prev.appendChild(img);
    });
  });
  form.addEventListener("submit", function () {
    var b = form.querySelector('button[type="submit"]'); if (b) { setTimeout(function () { b.disabled = true; }, 0); }
  });
})();
