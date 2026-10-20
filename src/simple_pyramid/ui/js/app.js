// Главное окно: обработка событий из Python и действия пользователя.
// «Подневка» и «События» — отдельные окна (daily.html, events.html), здесь только кнопки их открытия.
"use strict";

const TARIFFS = ["t0", "t1", "t2"];
const TARIFF_LABELS = {t0: "TO", t1: "T1", t2: "T2"};
const COPY_TIP = "Нажмите, чтобы скопировать";
let routes = [], lastPath = null, meterLoaded = false;

// ---- отрисовка блоков ----------------------------------------------
function renderReadings(data, loading = false){
  const body = $("#readings tbody");
  body.innerHTML = TARIFFS.map(t => {
    const cell = dir => {
      if (loading) return `<span class="skeleton" style="min-width:5em"></span>`;
      const v = data ? data[dir][t] : null;
      // shimmer-target — мерцает при обновлении блока (старое значение под мерцанием)
      if (v === null || v === undefined) return `<span class="shimmer-target">${naHtml("—")}</span>`;
      // В буфер — как на экране, с запятой, но без пробелов-разделителей (14167,57)
      return `<span class="copyable shimmer-target" data-copy="${toCopyNumber(v)}" data-tip="${COPY_TIP}">${fmtNumber(v)}</span>`;
    };
    return `<tr><td class="t">${TARIFF_LABELS[t]}</td><td>${cell("aPlus")}</td><td>${cell("aMinus")}</td></tr>`;
  }).join("");
}

function renderRoutes(loading = false){
  fitWindowHeight(); // подгонка сработает после перерисовки (с задержкой)
  const box = $("#routes");
  if (loading){
    box.innerHTML = `<div class="route skeleton-row"><span class="dot"></span>
      <span class="addr skeleton"></span><span class="state">&nbsp;</span></div>`;
    return;
  }
  if (!routes.length){
    box.innerHTML = `<div class="route-empty">${naHtml("Маршрутов связи нет")}</div>`;
    return;
  }
  box.innerHTML = routes.map(r => {
    let addrHtml = escHtml(r.text);
    if (r.ip){
      const shown = r.ipText || r.ip;
      const idx = r.text.indexOf(shown);
      const chip = txt => `<span class="copyable" data-copy="${escHtml(r.ip)}" data-tip="${COPY_TIP}">${escHtml(txt)}</span>`;
      addrHtml = idx !== -1
        ? `${escHtml(r.text.substring(0, idx))}${chip(shown)}${escHtml(r.text.substring(idx + shown.length))}`
        : `${escHtml(r.text)} ${chip(`[${r.ip}]`)}`;
    }
    return `<div class="route" data-id="${r.id}">
      <span class="dot"></span>
      <span class="addr">${addrHtml}</span>
      <span class="state"></span>
      <button class="icon" data-retry="${r.id}" data-tip="Повторить пинг" data-tip-pos="left">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>
      </button>
    </div>`;
  }).join("");
}

function renderIdentity(m){
  setValue($("#m-model"), m.model);
  routes = m.routes || [];
  renderRoutes();
  meterLoaded = true;
  $("#btn-daily").disabled = false;
  $("#btn-hourly").disabled = false;
}

function renderInfo(info){
  const addr = $("#m-address"), acc = $("#m-account");
  setValue(addr, info?.address);
  addr.dataset.tip = info?.fullPath || "";
  if (info?.account && info.accountNumber){
    const idx = info.account.indexOf("№");
    setValue(acc, `${escHtml(info.account.substring(0, idx + 1))}<span class="copyable" data-copy="${escHtml(info.accountNumber)}" data-tip="${COPY_TIP}">${escHtml(info.accountNumber)}</span>`, true);
  } else {
    setValue(acc, info?.account);
  }
}

function renderReadingsPart(r){
  setSkeleton($("#m-time"), false);
  $("#m-time").textContent = r?.takenAt ? fmtDateTime(r.takenAt) : "";
}

// Блок «Нагрузка»: реле с цветной точкой, лимит в кВт; время получения — в рамке справа,
// чтобы не спорить со значениями
function renderLoad(load){
  const relay = $("#m-relay");
  if (load?.relay){
    const dot = load.relayOn === true ? "ok" : load.relayOn === false ? "err" : "";
    setValue(relay, `<span class="dot ${dot}"></span>${escHtml(load.relay)}`, true);
  } else setValue(relay, null);
  setValue($("#m-limit"), load?.limitKw != null ? `${fmtNumber(load.limitKw)} кВт` : null);

  const at = $("#m-load-at");
  setSkeleton(at, false);
  const latest = [load?.relayAt, load?.limitAt].filter(Boolean).sort().pop();
  at.textContent = latest ? fmtDateTime(latest) : "";
  at.dataset.tip = [
    load?.relayAt ? `Реле получено ${fmtDateTime(load.relayAt)}` : "",
    load?.limitAt ? `Лимит получен ${fmtDateTime(load.limitAt)}` : "",
  ].filter(Boolean).join("\n");
}

// Блок не загрузился — в его полях пишем «не загрузилось», причина в подсказке
const SECTION_FIELDS = {
  info: ["#m-address", "#m-account"],
  readings: ["#m-time"],
  load: ["#m-relay", "#m-limit"],
};
function renderSectionError(section, error){
  (SECTION_FIELDS[section] || []).forEach(id => setValue($(id), errHtml(error), true));
  if (section === "readings") renderReadings(null);
  if (section === "load"){ setSkeleton($("#m-load-at"), false); $("#m-load-at").textContent = ""; }
  if (section === "events"){ $("#btn-events").disabled = true; $("#btn-events").dataset.tip = `Журнал не загрузился: ${error}`; }
}

// Сводка журнала: счётчик важных на кнопке и алярм-иконка у типа счётчика
function renderEventsSummary(summary){
  const btn = $("#btn-events");
  btn.disabled = false;
  btn.dataset.tip = "События прибора";
  const badge = $("#ev-badge");
  badge.textContent = summary?.importantTotal || "";
  badge.classList.toggle("hidden", !summary?.importantTotal);
  badge.classList.toggle("err", !!summary?.alarms?.length);

  const alarm = $("#m-alarm");
  const alarms = summary?.alarms || [];
  alarm.classList.toggle("hidden", !alarms.length);
  alarm.dataset.tip = alarms.length
    ? "В истории прибора есть тревожные события:\n"
      + alarms.map(a => `• ${a.eventType} — ${a.count} раз, последнее ${fmtDateTime(a.lastAt)}`).join("\n")
      + "\n\nНажмите, чтобы открыть журнал"
    : "";
}

// Пустое состояние (до первого поиска / прибор не найден) или начало загрузки
const VALUE_FIELDS = ["#m-model", "#m-address", "#m-account", "#m-time", "#m-relay", "#m-limit", "#m-load-at"];
function resetMeter(loading){
  meterLoaded = false;
  document.body.classList.toggle("state-empty", !loading);
  ["#btn-daily", "#btn-hourly", "#btn-events"].forEach(id => { $(id).disabled = true; });
  $("#ev-badge").classList.add("hidden");
  $("#m-alarm").classList.add("hidden");
  VALUE_FIELDS.forEach(id => {
    const el = $(id);
    el.textContent = "";
    setSkeleton(el, loading);
  });
  renderReadings(null, loading);
  routes = [];
  renderRoutes(loading);
}

// ---- живой глаз на логотипе пустого состояния ------------------------
// Моргает с человеческой скоростью раз в несколько секунд (иногда дважды подряд),
// а зрачок следит за мышкой — немного крипово.
const EYE_BLINK_MS = 260;                  // полное моргание: закрыть + открыть
const EYE_BLINK_EVERY = [2500, 5500];      // пауза между морганиями, мс (случайно в диапазоне)
const EYE_DOUBLE_BLINK = 0.25;             // доля двойных морганий
const EYE_RANGE = {x: 34, y: 11};          // насколько далеко зрачок уходит от центра (единицы SVG)
const EYE_REACH_PX = 180;                  // дальше этого расстояния до мышки зрачок уже «в упоре»
const EYE_CENTER = {x: 128 / 256, y: 154 / 256}; // центр глаза в долях размера логотипа

const rand = ([a, b]) => a + Math.random() * (b - a);
const eyeVisible = () => document.body.classList.contains("state-empty") && !document.hidden;

function startEyeAnimation(){
  const lid = $(".es-lid"), pupil = $(".es-pupil");
  // «уменьшить движение» в Windows здесь не учитываем: глаз — задуманная фишка, а на рабочих ПК
  // эта настройка часто выключена целиком (анимации Windows отключены ради скорости)
  if (!lid) return;

  const blink = () => lid.animate(
    [{transform: "scaleY(1)"}, {transform: "scaleY(.06)", offset: .38},
     {transform: "scaleY(.06)", offset: .5}, {transform: "scaleY(1)"}],
    {duration: EYE_BLINK_MS, easing: "ease-in-out"});

  (function blinkLoop(){
    if (eyeVisible()){
      blink();
      if (Math.random() < EYE_DOUBLE_BLINK) setTimeout(blink, EYE_BLINK_MS + 120);
    }
    setTimeout(blinkLoop, rand(EYE_BLINK_EVERY));
  })();

  // зрачок смотрит на мышку: направление — на курсор, отклонение растёт с расстоянием
  const logo = $(".es-logo");
  document.addEventListener("mousemove", e => {
    if (!eyeVisible()) return;
    const r = logo.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width * EYE_CENTER.x);
    const dy = e.clientY - (r.top + r.height * EYE_CENTER.y);
    const dist = Math.hypot(dx, dy) || 1;
    const reach = Math.min(dist / EYE_REACH_PX, 1);
    const x = dx / dist * reach * EYE_RANGE.x, y = dy / dist * reach * EYE_RANGE.y;
    pupil.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
  });
}

// ---- высота окна по содержимому ------------------------------------
// Нижняя граница окна — низ последнего маршрута + статус-строка: пустого места снизу нет.
const EMPTY_STATE_HEIGHT = 300;   // высота области пустого состояния, px
const MAX_SCREEN_SHARE = 0.9;     // окно не выше 90% экрана
let fitTimer = null;

function neededHeight(){
  const bar = $("#bar").offsetHeight, footer = $("footer").offsetHeight;
  if (document.body.classList.contains("state-empty")) return bar + EMPTY_STATE_HEIGHT + footer;
  const rows = Array.from($("#routes").children).reduce((h, el) => h + el.offsetHeight, 0);
  const wrap = $("#routes-wrap");
  const border = wrap.offsetHeight - wrap.clientHeight;
  return wrap.offsetTop + border + rows + footer;
}

function fitWindowHeight(attempt = 0){
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => {
    const target = Math.min(neededHeight(), Math.round(screen.availHeight * MAX_SCREEN_SHARE));
    const delta = target - window.innerHeight;
    if (Math.abs(delta) <= 1 || !window.pywebview) return;
    api().fit_height(delta);
    // после ресайза меряем ещё раз (рамки окна/масштаб) — максимум 3 итерации
    if (attempt < 2) setTimeout(() => fitWindowHeight(attempt + 1), 200);
  }, 60);
}

// ---- события из Python ---------------------------------------------
window.onStatus = d => setStatus(d.text, d.kind || 'info');
// Ошибки — классическим окном; в статус-строке остаётся короткая отметка
window.onError = d => { showError(d); setStatus(d.title, 'err'); };
// Живой лог фоновой задачи: пока задача идёт, сообщение не гаснет
const TASK_TITLES = {readings: "Опрос показаний", load: "Опрос реле", events: "Чтение журнала", report: "Отчёт"};
const busySections = new Set();
window.onTaskLog = d => setStatus(`${TASK_TITLES[d.section] || "Задача"}: ${d.text}`, 'info',
                                  {sticky: busySections.has(d.section)});

window.onAuth = d => {
  // Логин показывается в заголовке окна Windows (его ставит Python)
  if (d.ok){
    show("#ov-login", false);
  } else {
    show("#ov-login", true);
    $("#li-err").textContent = d.error || "";
    $("#li-login").focus();
  }
};

window.onSearchStarted = () => { $("#btn-find").disabled = true; resetMeter(true); };
window.onSearchFailed = () => { $("#btn-find").disabled = false; resetMeter(false); };

window.onMeterPart = p => {
  if (p.error){
    renderSectionError(p.section, p.error);
    return;
  }
  switch (p.section){
    case "identity": renderIdentity(p.data); break;
    case "info": renderInfo(p.data); break;
    case "readings": renderReadingsPart(p.data); renderReadings(p.data); break;
    case "load": renderLoad(p.data); break;
    case "events": renderEventsSummary(p.data); break;
  }
  // кнопка «Найти» снова доступна, как только пришла хотя бы основа
  if (p.section === "identity") $("#btn-find").disabled = false;
  fitWindowHeight(); // высота карточек могла измениться
};

window.onSectionBusy = d => {
  if (d.busy) busySections.add(d.section); else busySections.delete(d.section);
  const card = {readings: "#card-readings", load: "#card-load"}[d.section];
  if (card) $(card).classList.toggle("busy", d.busy);
  document.querySelectorAll(`[data-refresh="${d.section}"]`).forEach(btn => {
    btn.classList.toggle("busy", d.busy);
    btn.dataset.tip = d.busy ? "Отменить обновление" : "Обновить";
  });
};

// ↻ — опросить прибор и обновить блок; во время опроса та же кнопка — «отменить»
document.addEventListener("click", e => {
  const btn = e.target.closest("[data-refresh]");
  if (!btn || !meterLoaded) return;
  const section = btn.dataset.refresh;
  if (btn.classList.contains("busy")) api().cancel(section);
  else api().refresh(section);
});

window.onPing = d => {
  const row = document.querySelector(`.route[data-id="${d.id}"]`);
  if (!row) return;
  row.querySelector(".dot").className = "dot " + d.state;
  const st = row.querySelector(".state");
  st.className = "state " + d.state;
  st.textContent = d.text;
};

// Прогресс выгрузки — только для выгрузок из этого окна (подневка выгружается из своего)
window.onExport = d => {
  if ((d.source || "main") !== "main") return;
  if (d.stage === "running"){
    $("#pr-title").textContent = "Формируется отчёт";
    $("#pr-text").textContent = "Подождите…";
    $("#pr-actions").classList.add("hidden");
    $("#pr-open").classList.remove("hidden");
    $(".spin").classList.remove("hidden");
    show("#ov-progress", true);
  }
  if (d.stage === "done"){
    lastPath = d.path;
    $("#pr-title").textContent = "Отчёт готов";
    $("#pr-text").textContent = d.path;
    $(".spin").classList.add("hidden");
    $("#pr-actions").classList.remove("hidden");
  }
  // причину покажет окно ошибки (событие Error)
  if (d.stage === "error") show("#ov-progress", false);
};

function showChangelog(title, changelog, isUpdate){
  $("#up-title").textContent = title;
  $("#up-log").innerHTML = renderChangelog(changelog);
  ["#up-later", "#up-now"].forEach(id => $(id).classList.toggle("hidden", !isUpdate));
  $("#up-ok").classList.toggle("hidden", isUpdate);
  show("#ov-update", true);
}
window.onUpdate = d => showChangelog(`Доступна версия ${d.version}`, d.changelog, true);
// первый запуск после обновления
window.onWhatsNew = d => showChangelog(`Что нового в версии ${d.version}`, d.changelog, false);
window.onUpdateStatus = d => {
  $("#pr-text").textContent = d.attempt > 0 ? `${d.message} · попытка ${d.attempt}` : d.message;
};
window.onUpdateProgress = d => {
  $("#pr-track").classList.remove("hidden");
  $(".spin").classList.add("hidden");
  $("#pr-fill").style.width = d.percent + "%";
  $("#pr-text").textContent = `${fmtBytes(d.downloaded)} из ${fmtBytes(d.total)}`;
};

// ---- действия ------------------------------------------------------
$("#btn-find").onclick = () => {
  const v = $("#meter").value.trim();
  if (!v){ setStatus("Введите номер ПУ", 'warn'); $("#meter").focus(); return; }
  api().search(v);
};
$("#meter").addEventListener("keydown", e => { if (e.key === "Enter") $("#btn-find").click(); });

$("#routes").addEventListener("click", e => {
  const btn = e.target.closest("[data-retry]");
  if (btn) api().ping(btn.dataset.retry);
});

// отдельные окна
$("#btn-daily").onclick = () => api().open_daily();
$("#btn-events").onclick = () => api().open_events(true);
$("#m-alarm").onclick = () => api().open_events(true);

$("#btn-user").onclick = () => api().logout();
$("#li-ok").onclick = () => {
  const l = $("#li-login").value.trim(), p = $("#li-pass").value.trim();
  if (!l || !p){ $("#li-err").textContent = "Заполните логин и пароль"; return; }
  $("#li-err").textContent = "";
  api().login(l, p, true);
};
$("#ov-login").addEventListener("keydown", e => { if (e.key === "Enter") $("#li-ok").click(); });

// Выгрузка почасовки
function openExport(title){
  $("#ex-title").textContent = title;
  $("#ex-err").textContent = "";
  if (!$("#ex-from").value) $("#ex-from").value = today();
  if (!$("#ex-to").value) $("#ex-to").value = today();
  show("#ov-export", true);
  checkExportPeriod();
}
$("#btn-hourly").onclick = () => openExport("Выгрузка почасовки");
// Проверка периода на лету: подсветка поля и текст ошибки, кнопка недоступна
function checkExportPeriod(){
  const err = validatePeriod($("#ex-from").value, $("#ex-to").value);
  $("#ex-from").classList.toggle("invalid", err?.field === "from");
  $("#ex-to").classList.toggle("invalid", err?.field === "to");
  $("#ex-err").textContent = err ? err.message : "";
  $("#ex-ok").disabled = !!err;
  return !err;
}
["#ex-from", "#ex-to"].forEach(id => {
  attachDateMask($(id));
  $(id).addEventListener("input", checkExportPeriod);
});
$("#ex-cancel").onclick = () => show("#ov-export", false);
$("#ex-browse").onclick = async () => {
  const dir = await api().browse_folder();
  if (dir) $("#ex-dir").value = dir;
};
$("#ex-ok").onclick = async () => {
  if (!checkExportPeriod()) return;
  const res = await api().export("hourly", $("#ex-from").value.trim(),
                                 $("#ex-to").value.trim(), $("#ex-dir").value.trim());
  if (res.ok) show("#ov-export", false);
  else $("#ex-err").textContent = res.error;
};

$("#pr-close").onclick = () => show("#ov-progress", false);
$("#pr-open").onclick = () => { if (lastPath) api().open_folder(lastPath); };

$("#up-later").onclick = () => show("#ov-update", false);
$("#up-ok").onclick = () => show("#ov-update", false);
$("#up-now").onclick = () => {
  show("#ov-update", false);
  $("#pr-title").textContent = "Обновление";
  $("#pr-text").textContent = "Подключение…";
  $("#pr-actions").classList.add("hidden");
  $("#pr-track").classList.add("hidden");
  $(".spin").classList.remove("hidden");
  show("#ov-progress", true);
  api().start_update();
};

// История сообщений статус-строки
$("#status").onclick = e => { e.stopPropagation(); $("#status-history").classList.toggle("hidden"); };
$("#status").addEventListener("keydown", e => { if (e.key === "Enter") $("#status").click(); });
document.addEventListener("click", e => {
  if (!e.target.closest("#status-history")) $("#status-history").classList.add("hidden");
});

// Окно ошибки
$("#er-close").onclick = () => show("#ov-error", false);
$("#er-copy").onclick = () => {
  const text = [$("#er-title").textContent, $("#er-message").textContent, $("#er-details-text").textContent]
    .filter(Boolean).join("\n\n");
  navigator.clipboard.writeText(text).then(() => setStatus("Подробности ошибки скопированы", 'ok'));
};

document.addEventListener("keydown", e => {
  if (e.key === "Escape"){
    ["#ov-export", "#ov-update", "#ov-error"].forEach(id => show(id, false));
    $("#status-history").classList.add("hidden");
  }
});

window.addEventListener("pywebviewready", async () => {
  resetMeter(false);
  startEyeAnimation();
  const info = await api().bootstrap();
  $("#version").textContent = "v" + info.version;
  if (info.mock) $("#mock-hint").classList.remove("hidden");
  if (info.state === "need_login"){ show("#ov-login", true); $("#li-login").focus(); }
  else setStatus(`Вход: ${info.login}…`, 'info');
  $("#meter").focus();
});
