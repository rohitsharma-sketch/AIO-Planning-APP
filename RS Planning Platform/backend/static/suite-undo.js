/* Suite undo / redo - served inside GET /api/suite-theme.js, so every app gets it.
   (user, 2026-10-08: "Add an undo button feature in all apps, Forward and Backward")

   Records every committed field edit (input / select / textarea / checkbox - the browser's
   'change' event) as {field, before, after}. Undo puts the old value back the way a person
   would: native value setter + 'input' + 'change' events, so plain-HTML handlers (BIS,
   Listing, Re-Aligner) and React onChange (AOP, Calendar, Sales Plan) both see a normal
   edit and recompute. Nothing is saved by undo itself - each app's own Save still applies.
   A field re-rendered since the edit is found again by id / data-key / name / aria-label.
   Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z) work when the cursor is not inside a text box (inside one,
   the browser's own typing undo applies). Opt a field out with data-no-undo.
   ponytail: field edits only - app actions (Clear all, drag, Re-seed) are not recorded;
   give the module an action hook when one of those needs undo. */
(function () {
  if (window.SuiteUndo) return;   // suite-theme.js re-loads itself when the tab is shown again
  var SEL = 'input,select,textarea';
  var SKIP = { password: 1, file: 1, hidden: 1, submit: 1, button: 1, reset: 1, image: 1 };
  var KEYS = ['id', 'data-key', 'data-bk', 'data-k', 'name', 'aria-label'];
  var MAX = 200;
  var past = [], future = [], focusVal = new WeakMap(), applying = false, ui = null;

  function editable(el) {
    return !!(el && el.matches && el.matches(SEL) && !SKIP[(el.type || '').toLowerCase()]
      && !el.closest('[data-no-undo]'));
  }
  function isBox(el) { return el.type === 'checkbox' || el.type === 'radio'; }
  function read(el) { return isBox(el) ? el.checked : el.value; }
  function locator(el) {
    for (var i = 0; i < KEYS.length; i++) {
      var v = el.getAttribute(KEYS[i]);
      if (!v) continue;
      var q = el.tagName.toLowerCase() + '[' + KEYS[i] + '="' + (window.CSS && CSS.escape ? CSS.escape(v) : v) + '"]';
      try { if (document.querySelectorAll(q).length === 1) return q; } catch (e) {}
    }
    return null;
  }
  function label(el) {
    var l = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('placeholder') || el.name || '';
    if (!l && el.id) { var f = document.querySelector('label[for="' + el.id + '"]'); if (f) l = f.textContent; }
    if (!l && el.closest('label')) l = el.closest('label').textContent;
    return (l || 'field').trim().replace(/\s+/g, ' ').slice(0, 60);
  }
  function show(v) { return typeof v === 'boolean' ? (v ? 'on' : 'off') : (v === '' ? '(blank)' : String(v).slice(0, 30)); }

  document.addEventListener('focusin', function (e) {
    if (editable(e.target)) focusVal.set(e.target, read(e.target));
  }, true);
  document.addEventListener('change', function (e) {
    var el = e.target;
    if (applying || !editable(el)) return;
    // value when focused; else the value the page drew it with (the window had no focus, or a script changed it)
    var after = read(el), before = focusVal.has(el) ? focusVal.get(el) : isBox(el) ? !after
      : el.tagName === 'SELECT' ? (Array.prototype.find.call(el.options, function (o) { return o.defaultSelected; }) || {}).value
      : el.defaultValue;
    focusVal.set(el, after);
    if (before === undefined || before === after) return;
    past.push({ el: el, loc: locator(el), name: label(el), before: before, after: after });
    if (past.length > MAX) past.shift();
    future = [];
    paint();
  }, true);   // capture: runs before the app's own handler re-renders the field away

  function find(r) {
    if (r.el && r.el.isConnected) return r.el;
    return r.loc ? document.querySelector(r.loc) : null;
  }
  function put(el, v) {
    applying = true;
    try {
      if (isBox(el)) { if (el.checked !== v) el.click(); }
      else {
        var proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype
          : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);   // React sees the change
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    } finally { applying = false; }
  }
  function step(from, to, back) {
    var r = from.pop();
    if (!r) return;
    var el = find(r);
    if (!el) { toast('"' + r.name + '" is no longer on screen - skipped'); paint(); return; }
    var v = back ? r.before : r.after;
    put(el, v);
    el = find({ el: el, loc: r.loc }) || el;   // the app may have re-rendered it
    focusVal.set(el, v);
    r.el = el;
    to.push(r);
    if (el.isConnected) { el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); flash(el); }
    toast((back ? 'Undone: ' : 'Redone: ') + r.name + ' → ' + show(v));
    paint();
  }
  function undo() { step(past, future, true); }
  function redo() { step(future, past, false); }

  document.addEventListener('keydown', function (e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    var k = (e.key || '').toLowerCase();
    if (k !== 'z' && k !== 'y') return;
    var a = document.activeElement;
    if (a && (a.isContentEditable || (a.matches && a.matches('textarea,input:not([type=checkbox]):not([type=radio]):not([type=range])')))) return;
    if (k === 'y' || e.shiftKey) { if (!future.length) return; redo(); }
    else { if (!past.length) return; undo(); }
    e.preventDefault();
  });

  function flash(el) {
    var o = el.style.outline, f = el.style.outlineOffset;
    el.style.outline = '2px solid var(--st-accent, #2F6F5E)'; el.style.outlineOffset = '1px';
    setTimeout(function () { el.style.outline = o; el.style.outlineOffset = f; }, 900);
  }
  var tEl = null, tT = 0;
  function toast(msg) {
    if (!tEl) {
      tEl = document.createElement('div');
      tEl.setAttribute('role', 'status');
      tEl.style.cssText = 'position:fixed;left:16px;bottom:64px;z-index:2147483646;max-width:min(420px,calc(100% - 32px));'
        + 'padding:7px 12px;border-radius:8px;background:#1F2A33;color:#fff;font:500 12.5px/1.35 system-ui,sans-serif;'
        + 'box-shadow:0 4px 14px rgba(0,0,0,.25);transition:opacity .2s;pointer-events:none';
      document.body.appendChild(tEl);
    }
    tEl.textContent = msg; tEl.style.opacity = '1';
    clearTimeout(tT); tT = setTimeout(function () { tEl.style.opacity = '0'; }, 2600);
  }

  function btn(txt, fn) {
    var b = document.createElement('button');
    b.type = 'button'; b.innerHTML = txt;
    b.style.cssText = 'border:0;background:transparent;color:inherit;font:600 13px/1 system-ui,sans-serif;'
      + 'padding:8px 12px;display:flex;align-items:center;gap:5px;border-radius:999px';
    b.onclick = fn;
    return b;
  }
  function build() {
    ui = document.createElement('div');
    ui.setAttribute('role', 'group'); ui.setAttribute('aria-label', 'Undo and redo');
    ui.setAttribute('data-no-undo', '');
    ui.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:2147483646;display:none;align-items:center;'
      + 'border:1px solid var(--st-border, #D9D2C3);border-radius:999px;background:var(--st-surface, #fff);'
      + 'color:var(--st-ink, #1F2A33);box-shadow:0 3px 12px rgba(0,0,0,.14)';
    ui.u = btn('&#x21B6; Undo', undo);
    ui.r = btn('Redo &#x21B7;', redo);
    var sep = document.createElement('span');
    sep.style.cssText = 'width:1px;height:18px;background:var(--st-border, #D9D2C3)';
    ui.appendChild(ui.u); ui.appendChild(sep); ui.appendChild(ui.r);
    document.body.appendChild(ui);
  }
  function paint() {
    if (!document.body) return;
    if (!ui) build();
    // shown on pages that have something to edit (not Landing / sign-in pages)
    var has = past.length || future.length
      || (!document.querySelector('input[type=password]') && Array.prototype.some.call(document.querySelectorAll(SEL), editable));
    ui.style.display = has ? 'flex' : 'none';
    [[ui.u, past, 'Undo', ' (Ctrl+Z)'], [ui.r, future, 'Redo', ' (Ctrl+Y)']].forEach(function (x) {
      var r = x[1][x[1].length - 1];
      x[0].disabled = !r;
      x[0].style.opacity = r ? '1' : '.4';
      x[0].style.cursor = r ? 'pointer' : 'default';
      x[0].title = r ? x[2] + ': ' + r.name + ' → ' + show(x[2] === 'Undo' ? r.before : r.after) + x[3] : 'Nothing to ' + x[2].toLowerCase();
      x[0].setAttribute('aria-label', x[0].title);
    });
  }
  window.SuiteUndo = { undo: undo, redo: redo };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', paint); else paint();
  setInterval(paint, 2000);   // single-page apps add their fields after load
})();
