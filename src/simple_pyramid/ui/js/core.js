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

// ---- статус-строка ------------------------------------------------
function setStatus(text, type = 'info') {
  const icon = $("#status-icon");
  const txt = $("#status-text");
  const status = $("#status");

  const icons = {ok: '✓', err: '✕', warn: '⚠', info: ''};

  icon.textContent = icons[type] || '';
  icon.className = `icon-${type}`;
  txt.textContent = text;
  txt.title = text;

  // удаляем и сразу добавляем класс, чтобы перезапустить анимацию
  status.classList.remove('status-updated');
  void status.offsetWidth; // триггерим reflow
  status.classList.add('status-updated');
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
