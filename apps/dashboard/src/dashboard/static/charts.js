// Grafici del pannello (storia B13). Ogni grafico ha una tabella equivalente nella pagina.
// Monocromatici: colori letti dai token del design system (--ink, --graphite, --silver),
// serie distinte da tratteggio e forma dei punti, non dal colore.
(function () {
  if (typeof Chart === "undefined") { return; }
  var css = getComputedStyle(document.documentElement);
  function token(name, fallback) { return (css.getPropertyValue(name) || "").trim() || fallback; }
  var ink = token("--ink", "#111214");
  var graphite = token("--graphite", "#4A4D55");
  var pewter = token("--pewter", "#5E626B");
  var silver = token("--silver", "#C6C8CE");
  var mist = token("--mist", "#E4E5E9");
  var sheet = token("--sheet", "#FFFFFF");
  var sans = token("--sans", "system-ui, sans-serif");

  var dashes = [[], [6, 4], [2, 3], [10, 4, 2, 4], [1, 5], [14, 6]];
  var points = ["circle", "rect", "triangle", "rectRot", "crossRot", "star"];
  var lines = [ink, graphite, ink, graphite, ink, graphite];

  Chart.defaults.font.family = sans;
  Chart.defaults.color = graphite;
  Chart.defaults.borderColor = mist;

  document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
    var source = document.getElementById(canvas.dataset.chart);
    if (!source) { return; }
    var data = JSON.parse(source.textContent);
    var type = canvas.dataset.type || "line";
    var datasets = data.series.map(function (s, i) {
      if (type === "bar") {
        // Prima: argento con bordo grafite; dopo: inchiostro pieno.
        var filled = i % 2 === 1;
        return { label: s.label, data: s.data, borderWidth: 1.5, borderRadius: 4,
                 backgroundColor: filled ? ink : silver, borderColor: filled ? ink : graphite };
      }
      return { label: s.label, data: s.data, spanGaps: false, tension: 0,
               borderColor: lines[i % lines.length], backgroundColor: sheet,
               borderDash: dashes[i % dashes.length], borderWidth: 2,
               pointStyle: points[i % points.length], pointRadius: 4, pointHoverRadius: 6,
               pointBorderColor: lines[i % lines.length], pointBackgroundColor: sheet, pointBorderWidth: 1.5 };
    });
    new Chart(canvas, {
      type: type,
      // Etichette lunghe ("servizio · requisito") su piu' righe, senza rotazione.
      data: { labels: data.labels.map(function (l) { return type === "bar" ? String(l).split(" · ") : l; }), datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { position: "bottom", labels: { color: ink, usePointStyle: type !== "bar", boxWidth: 28, padding: 16 } },
          tooltip: { backgroundColor: ink, titleColor: sheet, bodyColor: sheet, borderColor: ink, displayColors: true,
                     callbacks: { label: function (c) { return c.dataset.label + ": " + (c.parsed.y === null ? "dati insufficienti" : c.parsed.y + "%"); } } }
        },
        scales: {
          x: { grid: { display: false }, border: { color: silver },
               ticks: { color: pewter, maxRotation: type === "bar" ? 0 : 50, autoSkip: type !== "bar" } },
          y: { beginAtZero: true, suggestedMax: canvas.dataset.max ? Number(canvas.dataset.max) : undefined,
               grid: { color: mist }, border: { display: false },
               ticks: { color: pewter, callback: function (v) { return v + "%"; } } }
        }
      }
    });
  });
})();
