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
