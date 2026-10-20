// Окно «Подневка»: показания A+ на начало суток и расход за сутки.
// Данные приходят одним запросом (даже год — ~1100 чисел), а строки дорисовываются
// порциями по мере прокрутки, чтобы большой период открывался мгновенно.
"use strict";

const DAILY_BATCH = 60;          // строк за одну дорисовку
const SCROLL_PRELOAD_PX = 200;   // дорисовываем, когда до низа осталось столько
let dailyRows = [], dailyRendered = 0, shownPeriod = null;

function fmtDate(d){ return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`; }

// Быстрые периоды: от начала месяца/N месяцев назад до сегодня
function dailyRange(kind){
  const t = new Date(); t.setHours(0, 0, 0, 0);
  const from = new Date(t);
  if (kind === "month") from.setDate(1);
  if (kind === "prev"){
    return [new Date(t.getFullYear(), t.getMonth() - 1, 1), new Date(t.getFullYear(), t.getMonth(), 0)];
  }
  const months = {"3m": 3, "6m": 6, "9m": 9, year: 12}[kind];
  if (months) from.setMonth(from.getMonth() - months);
  return [from, t];
}

function dailyCell(v){
  if (v === null || v === undefined) return `<td>${naHtml("—")}</td>`;
  return `<td><span class="copyable" data-copy="${toCopyNumber(v)}" data-tip="Нажмите, чтобы скопировать">${fmtNumber(v)}</span></td>`;
}

function renderDailyBatch(){
  const next = dailyRows.slice(dailyRendered, dailyRendered + DAILY_BATCH);
  $("#dv-rows").insertAdjacentHTML("beforeend", next.map(r => `<tr>
      <td>${fmtDateTime(r.day)}</td>${dailyCell(r.t0)}${dailyCell(r.t1)}${dailyCell(r.t2)}${dailyCell(r.consumption)}
    </tr>`).join(""));
  dailyRendered += next.length;
}

function dailySkeleton(){
  $("#dv-rows").innerHTML = Array.from({length: 10}, () =>
    `<tr>${"<td><span class=\"skeleton\"></span></td>".repeat(5)}</tr>`).join("");
}

function emptyRow(text){
  $("#dv-rows").innerHTML = `<tr><td colspan="5" class="table-empty">${naHtml(text)}</td></tr>`;
}

function markPeriod(){
  const err = validatePeriod($("#dv-from").value, $("#dv-to").value);
  $("#dv-from").classList.toggle("invalid", err?.field === "from");
  $("#dv-to").classList.toggle("invalid", err?.field === "to");
  $("#dv-err").textContent = err ? err.message : "";
  return !err;
}

async function loadDaily(){
  if (!markPeriod()) return;
  const from = $("#dv-from").value, to = $("#dv-to").value;
  $("#dv-show").disabled = true;
  $("#dv-download").disabled = true;
  $("#dv-summary").textContent = "";
  dailySkeleton();
  const res = await api().daily_view(from, to);
  $("#dv-show").disabled = false;
  if (!res.ok){
    emptyRow("Не удалось загрузить");
    $("#dv-err").textContent = res.error;
    return;
  }
  // свежие дни сверху
  dailyRows = res.rows.slice().reverse();
  dailyRendered = 0;
  $("#dv-rows").innerHTML = "";
  $("#dv-body").scrollTop = 0;
  if (!dailyRows.some(r => r.t0 !== null)){ emptyRow("За этот период показаний нет"); return; }
  renderDailyBatch();
  shownPeriod = [from, to];
  $("#dv-download").disabled = false;

  // итог: расход за период по общему показанию
  const filled = res.rows.filter(r => r.t0 !== null);
  const first = filled[0], last = filled[filled.length - 1];
  const total = Math.round((last.t0 - first.t0) * 1000) / 1000;
  $("#dv-summary").innerHTML = `Расход ${fmtDateTime(first.day)} – ${fmtDateTime(last.day)}: `
    + `<b>${fmtNumber(total)} кВт·ч</b> · дней с показаниями ${filled.length} из ${res.rows.length}`;
}

function setPeriod(from, to){
  $("#dv-from").value = fmtDate(from);
  $("#dv-to").value = fmtDate(to);
}

// ---- действия ------------------------------------------------------
["#dv-from", "#dv-to"].forEach(id => {
  attachDateMask($(id));
  $(id).addEventListener("keydown", e => { if (e.key === "Enter") loadDaily(); });
  $(id).addEventListener("input", () => {
    document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
    $("#dv-download").disabled = true; // скачивать — только то, что показано
  });
});
$("#dv-show").onclick = loadDaily;
document.querySelectorAll(".chip").forEach(chip => chip.onclick = () => {
  setPeriod(...dailyRange(chip.dataset.range));
  document.querySelectorAll(".chip").forEach(c => c.classList.toggle("active", c === chip));
  loadDaily();
});

// «Скачать xlsx» — диалог папки поверх этого окна, затем выгрузка показанного периода
$("#dv-download").onclick = async () => {
  if (!shownPeriod) return;
  const res = await api().export_here("daily", shownPeriod[0], shownPeriod[1], "daily");
  if (!res.ok && !res.cancelled) $("#dv-err").textContent = res.error;
};
window.onExport = d => {
  if (d.source !== "daily") return;
  const box = $("#dv-export");
  if (d.stage === "running") box.innerHTML = `<span class="icon-info">Сохраняю xlsx…</span>`;
  if (d.stage === "done"){
    box.innerHTML = `<span class="icon-ok">✓</span> Сохранено <button class="linkbtn" id="dv-open">Открыть папку</button>`;
    $("#dv-open").onclick = () => api().open_folder(d.path);
  }
  if (d.stage === "error") box.innerHTML = `<span class="icon-err">Не удалось сохранить: ${escHtml(d.error)}</span>`;
};

// дорисовка по прокрутке
$("#dv-body").addEventListener("scroll", () => {
  const b = $("#dv-body");
  if (b.scrollTop + b.clientHeight >= b.scrollHeight - SCROLL_PRELOAD_PX && dailyRendered < dailyRows.length) {
    renderDailyBatch();
  }
});

// в главном окне нашли другой прибор — показываем его подневку за тот же период
window.onMeterPart = p => { if (p.section === "identity" && !p.error) loadDaily(); };

window.addEventListener("pywebviewready", async () => {
  setPeriod(...dailyRange("month"));
  document.querySelector('.chip[data-range="month"]').classList.add("active");
  const ctx = await api().window_context();
  if (!ctx.meter){ emptyRow("Сначала найдите прибор в главном окне"); return; }
  loadDaily();
});
