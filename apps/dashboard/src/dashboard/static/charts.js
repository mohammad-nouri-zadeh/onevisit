// Grafici del pannello (storia B13). Ogni grafico ha una tabella equivalente nella pagina.
document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
  if (typeof Chart === "undefined") { return; }
  var source = document.getElementById(canvas.dataset.chart);
  if (!source) { return; }
  var data = JSON.parse(source.textContent);
  var palette = ["#0b5cad", "#b3471d", "#2f6f3e", "#6b3fa0", "#8a6d00", "#444444"];
  new Chart(canvas, {
    type: canvas.dataset.type || "line",
    data: {
      labels: data.labels,
      datasets: data.series.map(function (s, i) {
        return { label: s.label, data: s.data, borderColor: palette[i % palette.length],
                 backgroundColor: palette[i % palette.length], spanGaps: false };
      })
    },
    options: { responsive: true, animation: false,
               scales: { y: { beginAtZero: true, suggestedMax: canvas.dataset.max ? Number(canvas.dataset.max) : undefined } } }
  });
});
