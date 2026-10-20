// Просмотр подневки в программе: показания A+ на начало суток и расход за сутки.
// Данные приходят одним запросом (даже год — ~1100 чисел), а строки дорисовываются
// порциями по мере прокрутки, чтобы большой период открывался мгновенно.
"use strict";

const DAILY_BATCH = 60;          // строк за одну дорисовку
const DAILY_MIN_HEIGHT = 640;    // на время просмотра окно вырастает минимум до этой высоты
let dailyRows = [], dailyRendered = 0, dailyObserver = null;

function fmtDate(d){ return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`; }

// Быстрые периоды
function dailyRange(kind){
  const t = new Date(); t.setHours(0, 0, 0, 0);
  const from = new Date(t);
  if (kind === "month") from.setDate(1);
  if (kind === "prev"){
    const start = new Date(t.getFullYear(), t.getMonth() - 1, 1);
    const end = new Date(t.getFullYear(), t.getMonth(), 0);
    return [start, end];
  }
  if (kind === "3m") from.setMonth(from.getMonth() - 3);
  if (kind === "year") from.setFullYear(from.getFullYear() - 1);
  return [from, t];
}

function dailyCell(v, cls = ""){
  if (v === null || v === undefined) return `<td class="${cls}">${naHtml("—")}</td>`;
  return `<td class="${cls}"><span class="copyable" data-copy="${toCopyNumber(v)}">${fmtNumber(v)}</span></td>`;
}

function renderDailyBatch(){
  const body = $("#dv-rows");
  const next = dailyRows.slice(dailyRendered, dailyRendered + DAILY_BATCH);
  body.insertAdjacentHTML("beforeend", next.map(r => `<tr>
      <td class="left">${fmtDateTime(r.day)}</td>
      ${dailyCell(r.t0)}${dailyCell(r.t1)}${dailyCell(r.t2)}${dailyCell(r.consumption)}
    </tr>`).join(""));
  dailyRendered += next.length;
}

function dailySkeleton(){
  $("#dv-rows").innerHTML = Array.from({length: 8}, () =>
    `<tr><td class="left"><span class="skeleton"></span></td>${"<td><span class=\"skeleton\"></span></td>".repeat(4)}</tr>`
  ).join("");
}

async function loadDaily(){
  const err = validatePeriod($("#dv-from").value, $("#dv-to").value);
  $("#dv-from").classList.toggle("invalid", err?.field === "from");
  $("#dv-to").classList.toggle("invalid", err?.field === "to");
  $("#dv-err").textContent = err ? err.message : "";
  if (err) return;

  $("#dv-show").disabled = true;
  $("#dv-download").disabled = true;
  $("#dv-summary").textContent = "";
  dailySkeleton();
  const res = await api().daily_view($("#dv-from").value, $("#dv-to").value);
  $("#dv-show").disabled = false;
  if (!res.ok){
    $("#dv-rows").innerHTML = `<tr><td colspan="5" class="table-empty">${naHtml("Не удалось загрузить")}</td></tr>`;
    $("#dv-err").textContent = res.error;
    return;
  }
  // свежие сверху
  dailyRows = res.rows.slice().reverse();
  dailyRendered = 0;
  $("#dv-rows").innerHTML = "";
  $("#dv-body").scrollTop = 0;
  if (!dailyRows.some(r => r.t0 !== null)){
    $("#dv-rows").innerHTML = `<tr><td colspan="5" class="table-empty">${naHtml("За этот период показаний нет")}</td></tr>`;
    return;
  }
  renderDailyBatch();
  $("#dv-download").disabled = false;

  // итог: расход за период по общему показанию
  const filled = res.rows.filter(r => r.t0 !== null);
  const first = filled[0], last = filled[filled.length - 1];
  const total = last.t0 - first.t0;
  $("#dv-summary").innerHTML = `Расход с ${fmtDateTime(first.day)} по ${fmtDateTime(last.day)}: `
    + `<b style="color:var(--text)">${fmtNumber(Math.round(total * 1000) / 1000)} кВт·ч</b>`
    + ` · дней с показаниями ${filled.length} из ${res.rows.length}`;
}

function openDaily(){
  $("#dv-meter").textContent = $("#m-model").textContent + " · №" + ($("#meter").value.trim());
  if (!$("#dv-from").value){
    const [f, t] = dailyRange("month");
    $("#dv-from").value = fmtDate(f); $("#dv-to").value = fmtDate(t);
  }
  document.querySelectorAll("#ov-daily .chip").forEach(c => c.classList.remove("active"));
  $("#ov-daily").classList.add("show");
  if (window.innerHeight < DAILY_MIN_HEIGHT && window.pywebview) api().fit_height(DAILY_MIN_HEIGHT - window.innerHeight);
  loadDaily();
}

function closeDaily(){
  $("#ov-daily").classList.remove("show");
  fitWindowHeight();
}

["#dv-from", "#dv-to"].forEach(id => {
  attachDateMask($(id));
  $(id).addEventListener("keydown", e => { if (e.key === "Enter") loadDaily(); });
  $(id).addEventListener("input", () => {
    document.querySelectorAll("#ov-daily .chip").forEach(c => c.classList.remove("active"));
    $("#dv-download").disabled = true; // скачивать — только то, что показано
  });
});
$("#dv-show").onclick = loadDaily;
$("#dv-close").onclick = closeDaily;
document.querySelectorAll("#ov-daily .chip").forEach(chip => chip.onclick = () => {
  const [f, t] = dailyRange(chip.dataset.range);
  $("#dv-from").value = fmtDate(f); $("#dv-to").value = fmtDate(t);
  document.querySelectorAll("#ov-daily .chip").forEach(c => c.classList.toggle("active", c === chip));
  loadDaily();
});
// «Скачать xlsx» — то же окно выгрузки, период подставлен
$("#dv-download").onclick = () => {
  $("#ex-from").value = $("#dv-from").value;
  $("#ex-to").value = $("#dv-to").value;
  openExport("daily", "Выгрузка подневки");
};

// дорисовка по прокрутке
dailyObserver = new IntersectionObserver(entries => {
  if (entries.some(e => e.isIntersecting) && dailyRendered < dailyRows.length) renderDailyBatch();
}, {root: $("#dv-body"), rootMargin: "200px"});
dailyObserver.observe($("#dv-sentinel"));
