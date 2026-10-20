// Общее для дополнительных окон: короткие сообщения в нижней полосе (#strip-msg)
// вместо большой статус-строки главного окна. Переопределяет setStatus из core.js.
"use strict";

let stripTimer = null;

function setStatus(text, type = "info"){
  const msg = document.querySelector("#strip-msg");
  if (!msg) return;
  msg.className = `icon-${type}`;
  msg.textContent = text;
  clearTimeout(stripTimer);
  stripTimer = setTimeout(() => { msg.textContent = ""; }, STATUS_VISIBLE_MS);
}

// Ошибки из Python (например, не удалось вычитать журнал) — в полосу снизу
window.onError = d => setStatus(`${d.title}: ${d.message}`.replace(/\n/g, " "), "err");
