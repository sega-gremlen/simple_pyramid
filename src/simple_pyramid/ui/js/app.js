// Главное окно: обработка событий из Python и действия пользователя.
"use strict";

const TARIFFS = ["t0", "t1", "t2"];
const TARIFF_LABELS = {t0: "TO", t1: "T1", t2: "T2"};
let routes = [], lastPath = null, meterLoaded = false;

// ---- отрисовка блоков ----------------------------------------------
function renderReadings(data, loading = false){
  const body = $("#readings tbody");
  body.innerHTML = TARIFFS.map(t => {
    const cell = dir => {
      if (loading) return `<span class="cell skeleton"></span>`;
      const v = data ? data[dir][t] : null;
      if (v === null || v === undefined) return naHtml("—");
      // В буфер — как на экране, с запятой, но без пробелов-разделителей (14167,57)
      return `<span class="copyable" data-copy="${toCopyNumber(v)}" title="Копировать">${fmtNumber(v)}</span>`;
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
      const chip = txt => `<span class="copyable" data-copy="${escHtml(r.ip)}" title="Копировать IP">${escHtml(txt)}</span>`;
      addrHtml = idx !== -1
        ? `${escHtml(r.text.substring(0, idx))}${chip(shown)}${escHtml(r.text.substring(idx + shown.length))}`
        : `${escHtml(r.text)} ${chip(`[${r.ip}]`)}`;
    }
    return `<div class="route" data-id="${r.id}">
      <span class="dot"></span>
      <span class="addr" title="${escHtml(r.text)}">${addrHtml}</span>
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
  addr.title = info?.fullPath || "";
  if (info?.account && info.accountNumber){
    const idx = info.account.indexOf("№");
    setValue(acc, `${escHtml(info.account.substring(0, idx + 1))}<span class="copyable" data-copy="${escHtml(info.accountNumber)}" title="Копировать номер">${escHtml(info.accountNumber)}</span>`, true);
  } else {
    setValue(acc, info?.account);
  }
}

function renderReadingsPart(r){
  setSkeleton($("#m-time"), false);
  $("#m-time").textContent = r?.takenAt ? fmtDateTime(r.takenAt) : "";
  renderReadings(r);
}

// Блок не загрузился — в его полях пишем «не загрузилось», причина в подсказке
const SECTION_FIELDS = {
  info: ["#m-address", "#m-account"],
  readings: ["#m-time"],
};
function renderSectionError(section, error){
  (SECTION_FIELDS[section] || []).forEach(id => setValue($(id), errHtml(error), true));
  if (section === "readings") renderReadings(null);
}

// Пустое состояние (до первого поиска / прибор не найден) или начало загрузки
function resetMeter(loading){
  meterLoaded = false;
  document.body.classList.toggle("state-empty", !loading);
  $("#btn-daily").disabled = true;
  $("#btn-hourly").disabled = true;
  ["#m-model", "#m-address", "#m-account", "#m-time"].forEach(id => {
    const el = $(id);
    el.textContent = "";
    setSkeleton(el, loading);
  });
  renderReadings(null, loading);
  routes = [];
  renderRoutes(loading);
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
    case "readings": renderReadingsPart(p.data); break;
  }
  // кнопка «Найти» снова доступна, как только пришла хотя бы основа
  if (p.section === "identity") $("#btn-find").disabled = false;
  fitWindowHeight(); // высота карточек могла измениться
};

window.onSectionBusy = d => {
  if (d.busy) busySections.add(d.section); else busySections.delete(d.section);
  const card = {readings: "#card-readings"}[d.section];
  if (card) $(card).classList.toggle("busy", d.busy);
};

window.onPing = d => {
  const row = document.querySelector(`.route[data-id="${d.id}"]`);
  if (!row) return;
  row.querySelector(".dot").className = "dot " + d.state;
  const st = row.querySelector(".state");
  st.className = "state " + d.state;
  st.textContent = d.text;
};

window.onExport = d => {
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

window.onUpdate = d => {
  $("#up-title").textContent = `Доступна версия ${d.version}`;
  $("#up-log").textContent = d.changelog;
  show("#ov-update", true);
};
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

$("#btn-user").onclick = () => api().logout();
$("#li-ok").onclick = () => {
  const l = $("#li-login").value.trim(), p = $("#li-pass").value.trim();
  if (!l || !p){ $("#li-err").textContent = "Заполните логин и пароль"; return; }
  $("#li-err").textContent = "";
  api().login(l, p, true);
};
$("#ov-login").addEventListener("keydown", e => { if (e.key === "Enter") $("#li-ok").click(); });

let exportKind = "daily";
function openExport(kind, title){
  exportKind = kind;
  $("#ex-title").textContent = title;
  $("#ex-err").textContent = "";
  if (!$("#ex-from").value) $("#ex-from").value = today();
  if (!$("#ex-to").value) $("#ex-to").value = today();
  show("#ov-export", true);
  checkExportPeriod();
}
$("#btn-daily").onclick = () => openExport("daily", "Выгрузка подневки");
$("#btn-hourly").onclick = () => openExport("hourly", "Выгрузка почасовки");
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
  const res = await api().export(exportKind, $("#ex-from").value.trim(),
                                 $("#ex-to").value.trim(), $("#ex-dir").value.trim());
  if (res.ok) show("#ov-export", false);
  else $("#ex-err").textContent = res.error;
};

$("#pr-close").onclick = () => show("#ov-progress", false);
$("#pr-open").onclick = () => { if (lastPath) api().open_folder(lastPath); };

$("#up-later").onclick = () => show("#ov-update", false);
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
  const info = await api().bootstrap();
  $("#version").textContent = "v" + info.version;
  if (info.mock) $("#mock-hint").classList.remove("hidden");
  if (info.state === "need_login"){ show("#ov-login", true); $("#li-login").focus(); }
  else setStatus(`Вход: ${info.login}…`, 'info');
  $("#meter").focus();
});
