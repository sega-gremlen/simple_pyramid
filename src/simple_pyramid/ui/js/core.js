// Общие помощники интерфейса: DOM, форматирование, статус-строка, копирование.
"use strict";

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const api = () => window.pywebview.api;

// Простое экранирование HTML
function escHtml(s) {
  return String(s ?? "").replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function pad2(n){ return String(n).padStart(2, "0"); }

function today(){
  const d = new Date();
  return `${pad2(d.getDate())}.${pad2(d.getMonth()+1)}.${d.getFullYear()}`;
}

// "2026-10-20T06:45:31" → "20.10.2026 06:45" (без Date(), чтобы не играть с таймзонами)
function fmtDateTime(iso){
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(iso);
  if (!m) return iso;
  return m[4] ? `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}` : `${m[3]}.${m[2]}.${m[1]}`;
}

// 14167.57 → "14 167,57"
function fmtNumber(v){
  return Number(v).toLocaleString("ru-RU", {maximumFractionDigits: 3});
}

// ---- даты периода (те же правила, что в domain/period.py) ----------
const MIN_YEAR = 2015;

// "ДД.ММ.ГГГГ" → Date (полночь) или null, если такой даты нет (67-е число, 30 февраля…)
function parseDate(text){
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(String(text).trim());
  if (!m) return null;
  const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(y, mo - 1, d);
  if (date.getFullYear() !== y || date.getMonth() !== mo - 1 || date.getDate() !== d) return null;
  return date;
}

// Ошибка периода или null. Возвращает {field: "from"|"to"|null, message}
function validatePeriod(fromText, toText){
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const check = (text, field) => {
    if (!String(text).trim()) return {field, message: "Укажите дату"};
    const d = parseDate(text);
    if (!d) return {field, message: `Неверная дата «${text}» — нужен формат ДД.ММ.ГГГГ`};
    if (d.getFullYear() < MIN_YEAR) return {field, message: `Дата слишком ранняя (не раньше ${MIN_YEAR} года)`};
    if (d > now) return {field, message: "Дата ещё не наступила"};
    return null;
  };
  const err = check(fromText, "from") || check(toText, "to");
  if (err) return err;
  if (parseDate(fromText) > parseDate(toText)) return {field: "from", message: "Начало периода позже окончания"};
  return null;
}

// Маска ввода даты: цифры, точки ставятся сами (20102026 → 20.10.2026)
function attachDateMask(input){
  input.setAttribute("inputmode", "numeric");
  input.setAttribute("maxlength", "10");
  input.setAttribute("placeholder", "ДД.ММ.ГГГГ");
  input.addEventListener("input", e => {
    if (e.inputType && e.inputType.startsWith("delete")) return;
    const digits = input.value.replace(/\D/g, "").slice(0, 8);
    let out = digits.slice(0, 2);
    if (digits.length > 2) out += "." + digits.slice(2, 4);
    if (digits.length > 4) out += "." + digits.slice(4);
    if (digits.length === 2 || digits.length === 4) out += ".";
    input.value = out;
  });
}

// Число для буфера обмена: десятичная запятая, без разделителя тысяч (14167.57 → "14167,57")
function toCopyNumber(v){
  return String(v).replace(".", ",");
}

function fmtBytes(b){
  const u=["Б","КБ","МБ","ГБ"]; let i=0;
  while(b>=1024 && i<u.length-1){ b/=1024; i++; }
  return i===0 ? `${Math.round(b)} ${u[i]}` : `${b.toFixed(1)} ${u[i]}`;
}

function show(id, on){ $(id).classList.toggle("show", on); }

// Поле «ещё грузится»: мерцает только значение, подпись остаётся
function setSkeleton(el, on){ el.classList.toggle("skeleton", on); }

// Значения нет — единый приглушённый вид (а не прочерки разной ширины)
function naHtml(text = "нет данных"){ return `<span class="na">${escHtml(text)}</span>`; }
function errHtml(error){
  return `<span class="na err" data-tip="${escHtml(error)}" data-tip-pos="top">не загрузилось</span>`;
}

// Заполнить поле значением (или «нет данных») и снять мерцание
function setValue(el, value, isHtml = false){
  setSkeleton(el, false);
  if (value === null || value === undefined || value === "") el.innerHTML = naHtml();
  else if (isHtml) el.innerHTML = value;
  else el.textContent = value;
}

// ---- статус-строка ------------------------------------------------
// Сообщение появляется, держится STATUS_VISIBLE_MS и плавно гаснет за STATUS_FADE_MS.
// Предупреждения и ошибки держатся дольше. Клик по строке — история сообщений.
const STATUS_VISIBLE_MS = 4000;
const STATUS_IMPORTANT_VISIBLE_MS = 9000;
const STATUS_FADE_MS = 1200;
// Обычное сообщение не перебивает свежее предупреждение раньше, чем через столько мс
const STATUS_WARN_HOLD_MS = 2500;
const STATUS_HISTORY_SIZE = 50;

const statusHistory = [];
let statusTimer = null, statusShownAt = 0, statusKind = "info", statusPending = null;

function setStatus(text, type = 'info', {sticky = false} = {}) {
  const now = Date.now();
  statusHistory.unshift({text, type, at: new Date()});
  statusHistory.length = Math.min(statusHistory.length, STATUS_HISTORY_SIZE);
  renderStatusHistory();

  // свежее предупреждение/ошибку не затираем мелочью — покажем её чуть позже
  const important = statusKind === "warn" || statusKind === "err";
  if (important && type !== "warn" && type !== "err" && now - statusShownAt < STATUS_WARN_HOLD_MS){
    clearTimeout(statusPending);
    statusPending = setTimeout(() => showStatus(text, type, sticky), STATUS_WARN_HOLD_MS - (now - statusShownAt));
    return;
  }
  showStatus(text, type, sticky);
}

function showStatus(text, type, sticky){
  const icons = {ok: '✓', err: '✕', warn: '⚠', info: '•'};
  const status = $("#status");
  $("#status-icon").textContent = icons[type] || '';
  $("#status-icon").className = `icon-${type}`;
  $("#status-text").textContent = text;
  status.title = "История сообщений";
  statusKind = type;
  statusShownAt = Date.now();

  // перезапускаем анимацию появления
  status.style.setProperty("--status-fade", `${STATUS_FADE_MS}ms`);
  status.classList.remove("shown", "fading");
  void status.offsetWidth; // триггерим reflow
  status.classList.add("shown");

  clearTimeout(statusTimer);
  if (sticky) return;
  const visible = type === "warn" || type === "err" ? STATUS_IMPORTANT_VISIBLE_MS : STATUS_VISIBLE_MS;
  statusTimer = setTimeout(() => status.classList.add("fading"), visible);
}

function renderStatusHistory(){
  const box = $("#status-history-list");
  if (!box) return;
  const time = d => `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  box.innerHTML = statusHistory.length
    ? statusHistory.map(s => `<div class="sh-row"><span class="sh-time">${time(s.at)}</span>
        <span class="icon-${s.type}">${{ok: '✓', err: '✕', warn: '⚠', info: '•'}[s.type] || ''}</span>
        <span class="sh-text">${escHtml(s.text)}</span></div>`).join("")
    : naHtml("Пока ничего не происходило");
}

// ---- окно ошибки ---------------------------------------------------
function showError({title, message, details}){
  $("#er-title").textContent = title || "Ошибка";
  $("#er-message").textContent = message || "";
  $("#er-details").classList.toggle("hidden", !details);
  $("#er-details-text").textContent = details || "";
  $("#er-details").open = false;
  show("#ov-error", true);
  $("#er-close").focus();
}

// ---- копирование по клику ------------------------------------------
document.addEventListener('click', e => {
  const copyEl = e.target.closest('.copyable');
  if (!copyEl || copyEl.dataset.copy === undefined) return;
  const val = copyEl.dataset.copy;
  navigator.clipboard.writeText(val).then(() => {
    copyEl.classList.add('flash');
    setTimeout(() => copyEl.classList.remove('flash'), 600);
    setStatus(`Скопировано: ${val}`, 'ok');
  }).catch(() => setStatus("Не удалось скопировать", 'err'));
});
