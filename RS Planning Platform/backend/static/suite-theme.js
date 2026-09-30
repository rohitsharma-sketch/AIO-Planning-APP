/* Suite theme runtime - served as GET /api/suite-theme.js, prefixed by the
   server with window.__SUITE_THEMES__ (suite-themes.json) and
   window.__SUITE_THEME__ (the saved choice). Every app loads it synchronously
   in <head>, so the colours are right on first paint. It sets --st-<role> (and
   --st-<role>-rgb) on :root; apps read them as var(--st-role, <sage hex>), so
   an app still looks right if this script can't be reached.
   Picking a theme on Landing saves it (POST /api/suite-theme); other open apps
   pick it up when their tab is shown again. */
(function () {
  if (window.SuiteTheme) {                      // a refresh() re-run: just apply the saved choice
    window.SuiteTheme.apply(window.__SUITE_THEME__);
    return;
  }
  var cfg = window.__SUITE_THEMES__ || { themes: {} };

  // Suite type (user, 2026-09-28: the "alternate look"): IBM Plex Sans for text, IBM Plex Mono for figures,
  // Fraunces for page titles. Apps read var(--st-font-body|mono|display, <their old font>), so they keep
  // their old face if this script or Google Fonts can't be reached.
  if (!document.getElementById('st-fonts')) {
    var fl = document.createElement('link');
    fl.id = 'st-fonts'; fl.rel = 'stylesheet';
    fl.href = 'https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600'
      + '&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap';
    document.head.appendChild(fl);
    var fr = document.documentElement.style;
    fr.setProperty('--st-font-body', "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif");
    fr.setProperty('--st-font-mono', "'IBM Plex Mono', ui-monospace, Consolas, monospace");
    fr.setProperty('--st-font-display', "'Fraunces', Georgia, 'Times New Roman', serif");
  }
  var base = (document.currentScript && document.currentScript.src) || '';
  var origin = base.replace(/\/api\/suite-theme\.js.*$/, '');

  function apply(id) {
    var t = cfg.themes[id] || cfg.themes[cfg['default']];
    if (!t) return;
    var html = document.documentElement, root = html.style;
    var changed = window.SuiteTheme.current !== id;
    // Chrome leaves elements that have a colour `transition` on the OLD value
    // when a variable changes live (until they re-layout), so switch with
    // transitions off for one frame. Not needed on first paint.
    var live = changed && window.SuiteTheme.current !== null && document.body;
    if (live) {
      if (!document.getElementById('st-switching')) {
        var css = document.createElement('style');
        css.id = 'st-switching';
        css.textContent = 'html[data-st-switching] *,html[data-st-switching] *::before,html[data-st-switching] *::after{transition:none!important}';
        document.head.appendChild(css);
      }
      html.setAttribute('data-st-switching', '');
    }
    Object.keys(t).forEach(function (k) {
      if (k === 'name' || k === 'desc') return;
      root.setProperty('--st-' + k.replace('_rgb', '-rgb'), t[k]);
    });
    html.setAttribute('data-suite-theme', id);
    if (live) {
      void document.body.offsetHeight;   // force the restyle while transitions are off
      requestAnimationFrame(function () { requestAnimationFrame(function () { html.removeAttribute('data-st-switching'); }); });
    }
    window.SuiteTheme.current = id;
    if (changed) window.dispatchEvent(new CustomEvent('suitethemechange', { detail: id }));
  }

  // Tab shown again -> re-load this script (a <script> needs no CORS) to pick up a newer choice
  function refresh() {
    var s = document.createElement('script');
    s.src = origin + '/api/suite-theme.js?t=' + Date.now();
    s.onload = s.onerror = function () { s.remove(); };
    document.head.appendChild(s);
  }

  window.SuiteTheme = {
    themes: cfg.themes,
    current: null,
    apply: apply,
    save: function (id) {                       // Landing's picker; needs a signed-in session
      apply(id);
      return fetch(origin + '/api/suite-theme', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: id }),
      }).then(function (r) { if (!r.ok) throw new Error('Theme not saved (' + r.status + ')'); return id; });
    },
  };
  // "Sign in as" banner (2026-09-30): while an admin has the suite open as someone else, every page says so
  // and offers the way back. Nothing shows for a normal sign-in.
  fetch(origin + '/api/auth/me', { credentials: 'include', cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (u) {
      if (!u || !u.signed_in_by) return;
      function show() {
        var d = document.createElement('div');
        d.setAttribute('role', 'status');
        d.style.cssText = 'position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:2147483647;'
          + 'display:flex;align-items:center;gap:12px;max-width:calc(100% - 32px);white-space:nowrap;padding:8px 8px 8px 16px;'
          + 'border-radius:999px;background:#7A4B00;color:#fff;font:600 13px/1.3 system-ui,sans-serif;'
          + 'box-shadow:0 4px 16px rgba(0,0,0,.25)';
        var t = document.createElement('span');
        t.textContent = 'Signed in as ' + u.username;
        t.style.cssText = 'min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
        d.title = u.signed_in_by.username + ' opened RS Planning as ' + u.username + ' (Users & access > Sign in as)';
        var b = document.createElement('button');
        b.type = 'button'; b.textContent = 'Back to admin';
        b.style.cssText = 'border:0;border-radius:999px;padding:6px 12px;background:#fff;color:#7A4B00;font:inherit;cursor:pointer;white-space:nowrap';
        b.onclick = function () {
          b.disabled = true;
          fetch(origin + '/api/auth/stop-sign-in-as', { method: 'POST', credentials: 'include' })
            .finally(function () { location.href = origin + '/auth/users'; });
        };
        d.appendChild(t); d.appendChild(b); document.body.appendChild(d);
      }
      if (document.body) show(); else document.addEventListener('DOMContentLoaded', show);
    }).catch(function () {});
  apply(window.__SUITE_THEME__);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
})();
