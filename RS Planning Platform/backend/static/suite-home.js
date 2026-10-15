/* "← Landing" in every app - served inside GET /api/suite-theme.js (like suite-undo.js), so every page has it.
   (user, 2026-10-15: "how can i navigate from the sales planengine to ladning, the landing arrow button should be
   there in every app core - additional - ALL")

   An app with its own "← Landing" link (a.home / #home-link: Re-Aligner, NSO, Growth vs LY, Listing, STR) keeps it,
   pointed at the right address here; every other app (Calendar, AOP Forecaster, BIS, Sales Plan) gets a small
   "← Landing" pill bottom-left (the undo pill sits just right of it). Address: this origin's "/" when the page came
   through Landing (port 7800, or a tunnel with no port), else Landing on this host's port 7800 - an app opened on its
   own port still gets back. Not shown on Landing itself or on the sign-in pages. */
(function () {
  if (window.__suiteHome) return;   // suite-theme.js re-loads itself when the tab is shown again
  window.__suiteHome = 1;
  var port = location.port, path = location.pathname;
  var via = port === '7800' || port === '';
  var url = via ? '/' : location.protocol + '//' + location.hostname + ':7800/';
  if (via && (path === '/' || path === '/index.html')) return;   // Landing itself
  if (/(^|\/)(login|reset-password|change-password)(\.html)?\/?$/.test(path)) return;   // sign-in pages
  function run() {
    var own = document.querySelectorAll('a.home, a#home-link');
    if (own.length) { Array.prototype.forEach.call(own, function (a) { a.href = url; }); return; }
    if (document.querySelector('[data-suite-home]')) return;
    var a = document.createElement('a');
    a.href = url;
    a.setAttribute('data-suite-home', '');
    a.setAttribute('data-no-undo', '');
    a.title = 'Back to the Planning Suite (Landing)';
    a.innerHTML = '&#x2190; Landing';
    a.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:2147483646;display:inline-flex;align-items:center;'
      + 'padding:8px 13px;border-radius:999px;text-decoration:none;font:600 13px/1 system-ui,sans-serif;'
      + 'border:1px solid var(--st-border, #D9D2C3);background:var(--st-surface, #fff);color:var(--st-ink, #1F2A33);'
      + 'box-shadow:0 3px 12px rgba(0,0,0,.14);touch-action:manipulation';
    document.body.appendChild(a);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
