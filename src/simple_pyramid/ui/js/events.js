// Журнал событий прибора и алярм-иконка.
// Весь журнал (10 лет) уже лежит в Python; сюда приходят порции по EVENTS_PAGE при прокрутке.
"use strict";

const EVENTS_PAGE = 10;           // событий за одну подгрузку
const EVENTS_MIN_HEIGHT = 600;    // на время просмотра окно вырастает минимум до этой высоты
let eventsOffset = 0, eventsHasMore = false, eventsLoading = false, eventsSummary = null;

// Сводка журнала пришла (при поиске ПУ или после «Получить актуальные данные»)
function renderEventsSummary(summary){
  eventsSummary = summary;
  $("#btn-events").disabled = false;
  const badge = $("#ev-badge");
  badge.textContent = summary?.importantTotal || "";
  badge.classList.toggle("hidden", !summary?.importantTotal);
  badge.classList.toggle("err", !!summary?.alarms?.length);

  // алярм-иконка рядом с типом счётчика
  const alarm = $("#m-alarm");
  const alarms = summary?.alarms || [];
  alarm.classList.toggle("hidden", !alarms.length);
  alarm.dataset.tip = alarms.length
    ? "В истории прибора есть тревожные события:\n"
      + alarms.map(a => `• ${a.eventType} — ${a.count} раз, последнее ${fmtDateTime(a.lastAt)}`).join("\n")
      + "\n\nНажмите, чтобы открыть журнал"
    : "";
  $("#ev-latest").textContent = summary?.latestAt ? `последнее событие ${fmtDateTime(summary.latestAt)}` : "";
  if ($("#ov-events").classList.contains("show")) reloadEvents();
}

function resetEvents(){
  eventsSummary = null;
  $("#btn-events").disabled = true;
  $("#ev-badge").classList.add("hidden");
  $("#m-alarm").classList.add("hidden");
}

function eventRow(e){
  const cls = e.alarm ? "ev-alarm" : e.important ? "ev-important" : "";
  return `<tr class="${cls}">
    <td class="left"><span class="shimmer-target">${fmtDateTime(e.dt)}<span class="sec">:${e.dt.slice(17, 19)}</span></span></td>
    <td class="left text"><span class="shimmer-target">${e.alarm ? '<span class="dot err"></span>' : ""}${escHtml(e.eventType)}</span></td>
    <td class="left text"><span class="shimmer-target">${e.description ? escHtml(e.description) : naHtml("—")}</span></td>
  </tr>`;
}

async function loadEventsPage(){
  if (eventsLoading || (!eventsHasMore && eventsOffset > 0)) return;
  eventsLoading = true;
  const page = await api().events_page(eventsOffset, EVENTS_PAGE, $("#ev-important").checked);
  eventsLoading = false;
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
  $("#ev-count").textContent = page.total ? `показано ${eventsOffset} из ${page.total}` : "";
  // если экран большой, а событий на нём мало — догружаем сразу
  const body = $("#ev-body");
  if (eventsHasMore && body.scrollHeight <= body.clientHeight + 40) loadEventsPage();
}

function reloadEvents(){
  eventsOffset = 0; eventsHasMore = false;
  $("#ev-body").scrollTop = 0;
  loadEventsPage();
}

function openEvents({importantOnly = true} = {}){
  $("#ev-meter").textContent = $("#m-model").textContent + " · №" + $("#meter").value.trim();
  $("#ev-important").checked = importantOnly;
  $("#ov-events").classList.add("show");
  if (window.innerHeight < EVENTS_MIN_HEIGHT && window.pywebview) api().fit_height(EVENTS_MIN_HEIGHT - window.innerHeight);
  reloadEvents();
}

function closeEvents(){
  $("#ov-events").classList.remove("show");
  fitWindowHeight();
}

// «Получить актуальные данные»: та же механика, что ↻ у блоков (секция events)
function setEventsBusy(busy){
  $("#ov-events .sheet-body").classList.toggle("busy", busy);
  const btn = $("#ev-refresh");
  btn.textContent = busy ? "Отменить" : "Получить актуальные данные";
  btn.classList.toggle("accent", busy);
}

$("#btn-events").onclick = () => openEvents();
$("#m-alarm").onclick = () => openEvents({importantOnly: true});
$("#ev-close").onclick = closeEvents;
$("#ev-important").onchange = reloadEvents;
$("#ev-refresh").onclick = () => {
  if ($("#ov-events .sheet-body").classList.contains("busy")) api().cancel("events");
  else api().refresh("events");
};

new IntersectionObserver(entries => {
  if (entries.some(e => e.isIntersecting) && eventsHasMore) loadEventsPage();
}, {root: $("#ev-body"), rootMargin: "150px"}).observe($("#ev-sentinel"));
