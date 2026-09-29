/*
 * Configuración v1 — vanilla JS (convención del repo: JS separado).
 * Solo ajustes honestos: negocio, PIN (con el actual), probar balanza.
 * Todo por sesión del POS (cookie), sin roles en v1.
 */
(function () {
  'use strict';

  const CSRF_TOKEN = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  const URLS = window.CFG_URLS || {};

  function $(sel) { return document.querySelector(sel); }

  function showToast(msg) {
    const t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': CSRF_TOKEN,
      },
      body: JSON.stringify(payload),
    });
    const json = await res.json().catch(() => ({}));
    return { ok: res.ok, json };
  }

  async function saveBiz(btn) {
    btn.disabled = true;
    try {
      const { ok, json } = await postJson(URLS.biz, {
        whatsapp_phone: ($('#cfg-whatsapp') || {}).value || '',
        is_open: !!($('#cfg-open') || {}).checked,
      });
      if (!ok || !json.success) {
        showToast((json && json.error) || 'No se pudo guardar');
        return;
      }
      showToast('Negocio actualizado');
    } catch (err) {
      showToast('Sin conexión con el servidor');
    } finally {
      btn.disabled = false;
    }
  }

  async function savePin(btn) {
    btn.disabled = true;
    try {
      const { ok, json } = await postJson(URLS.pin, {
        current_pin: ($('#cfg-pin-now') || {}).value || '',
        new_pin: ($('#cfg-pin-new') || {}).value || '',
        new_pin2: ($('#cfg-pin-new2') || {}).value || '',
      });
      if (!ok || !json.success) {
        showToast((json && json.error) || 'No se pudo cambiar el PIN');
        return;
      }
      ['#cfg-pin-now', '#cfg-pin-new', '#cfg-pin-new2'].forEach((sel) => {
        const el = $(sel);
        if (el) el.value = '';
      });
      showToast('PIN actualizado');
    } catch (err) {
      showToast('Sin conexión con el servidor');
    } finally {
      btn.disabled = false;
    }
  }

  async function testScale(btn) {
    btn.disabled = true;
    try {
      const res = await fetch(URLS.scale);
      const json = await res.json().catch(() => ({}));
      const out = $('#cfg-scale-out');
      if (!res.ok || !json.success) {
        if (out) {
          out.hidden = false;
          out.textContent = 'No responde: ' + (json.error || 'revisa cables y puerto');
        }
        return;
      }
      if (out) {
        out.hidden = false;
        out.textContent = `Lee ${json.data.weight_kg} kg. Balanza lista.`;
      }
    } catch (err) {
      showToast('Sin conexión con el servidor');
    } finally {
      btn.disabled = false;
    }
  }

  function wireUp() {
    const biz = $('#cfg-save-biz');
    if (biz) biz.addEventListener('click', () => saveBiz(biz));
    const pin = $('#cfg-save-pin');
    if (pin) pin.addEventListener('click', () => savePin(pin));
    const scale = $('#cfg-scale-test');
    if (scale) scale.addEventListener('click', () => testScale(scale));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireUp);
  } else {
    wireUp();
  }
})();
