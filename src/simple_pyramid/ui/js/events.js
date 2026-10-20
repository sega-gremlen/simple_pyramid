// Окно «События»: журнал прибора. Весь журнал (10 лет) уже лежит в Python;
// сюда приходят порции по EVENTS_PAGE по мере прокрутки.
"use strict";

const EVENTS_PAGE = 10;           // событий за одну подгрузку
const SCROLL_PRELOAD_PX = 120;    // подгружаем, когда до низа осталось столько
let eventsOffset = 0, eventsHasMore = false, eventsLoading = false, eventsGeneration = 0;

function eventRow(e){
  const cls = e.alarm ? "ev-alarm" : e.important ? "ev-important" : "";
  return `<tr class="${cls}">
    <td><span class="shimmer-target">${fmtDateTime(e.dt)}</span></td>
    <td class="text"><span class="shimmer-target">${e.alarm ? '<span class="dot err"></span>' : ""}${escHtml(e.eventType)}</span></td>
    <td class="text"><span class="shimmer-target">${e.description ? escHtml(e.description) : naHtml("—")}</span></td>
  </tr>`;
}

function needMore(){
  const b = $("#ev-body");
  return eventsHasMore && b.scrollTop + b.clientHeight >= b.scrollHeight - SCROLL_PRELOAD_PX;
}

async function loadEventsPage(){
  if (eventsLoading) return;
  eventsLoading = true;
  const generation = eventsGeneration;
  $("#ev-more").classList.toggle("hidden", eventsOffset === 0);
  const page = await api().events_page(eventsOffset, EVENTS_PAGE, $("#ev-important").checked);
  eventsLoading = false;
  $("#ev-more").classList.add("hidden");
  if (generation !== eventsGeneration) return loadEventsPage(); // фильтр сменили, пока ждали

  const rows = $("#ev-rows");
  if (eventsOffset === 0) rows.innerHTML = "";
  if (!page.total){
    rows.innerHTML = `<tr><td colspan="3" class="table-empty">${naHtml(
      $("#ev-important").checked ? "Важных событий нет" : "Событий нет")}</td></tr>`;
  } else {
    rows.insertAdjacentHTML("beforeend", page.items.map(eventRow).join(""));
  }
  eventsOffset = page.offset + page.items.length;
  eventsHasMore = page.hasMore;
  $("#ev-count").textContent = page.total ? `Показано ${eventsOffset} из ${page.total}` : "";
  // окно большое, а событий на нём мало (или уже долистали) — догружаем сразу
  if (needMore()) loadEventsPage();
}

function reloadEvents(){
  eventsGeneration++;
  eventsOffset = 0; eventsHasMore = false;
  $("#ev-body").scrollTop = 0;
  loadEventsPage();
}

function setEventsBusy(busy){
  $("#ev-body").classList.toggle("busy", busy);
  const btn = $("#ev-refresh");
  btn.classList.toggle("busy", busy);
  btn.dataset.tip = busy ? "Отменить обновление" : "Обновить данные — вычитать журнал с прибора";
}

// ---- события из Python ---------------------------------------------
// журнал перечитан (после «Обновить данные» или в главном окне открыт другой прибор)
window.onMeterPart = p => { if (p.section === "events" && !p.error) reloadEvents(); };
window.onSectionBusy = d => { if (d.section === "events") setEventsBusy(d.busy); };
window.onTaskLog = d => { if (d.section === "events") setStatus(d.text, "info"); };
window.onStatus = d => { if (/журнал/i.test(d.text)) setStatus(d.text, d.kind); };
// «События» открыли повторно с другим фильтром (например, по алярм-иконке)
window.onEventsFilter = d => {
  if ($("#ev-important").checked !== d.importantOnly){
    $("#ev-important").checked = d.importantOnly;
    reloadEvents();
  }
};

// ---- действия ------------------------------------------------------
$("#ev-important").onchange = reloadEvents;
$("#ev-refresh").onclick = () => {
  if ($("#ev-refresh").classList.contains("busy")) api().cancel("events");
  else api().refresh("events");
};
$("#ev-body").addEventListener("scroll", () => { if (needMore()) loadEventsPage(); });
window.addEventListener("resize", () => { if (needMore()) loadEventsPage(); });

window.addEventListener("pywebviewready", async () => {
  const ctx = await api().window_context();
  if (!ctx.meter){
    $("#ev-rows").innerHTML = `<tr><td colspan="3" class="table-empty">${naHtml("Сначала найдите прибор в главном окне")}</td></tr>`;
    return;
  }
  $("#ev-important").checked = ctx.importantOnly !== false;
  if (!ctx.eventsLoaded){
    $("#ev-rows").innerHTML = Array.from({length: 8}, () =>
      `<tr>${"<td><span class=\"skeleton\"></span></td>".repeat(3)}</tr>`).join("");
    return; // журнал ещё грузится — придёт событием MeterPart
  }
  reloadEvents();
});
