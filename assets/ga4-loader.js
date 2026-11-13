/* Basic editorial page views. The Google tag is loaded only after a visitor opts in. */
(() => {
  const id = document.currentScript?.dataset.measurementId;
  const page = new URL(window.location.href);
  const project = '/geo-platform-observation/';
  if (!/^G-[A-Z0-9]+$/.test(id || '') || page.protocol !== 'https:' ||
      page.hostname !== 'helen-bird.github.io' || !page.pathname.startsWith(project)) return;

  const blocked = navigator.globalPrivacyControl === true || navigator.doNotTrack === '1';
  const key = 'geo-analytics-preference-v1';
  const disabled = 'ga-disable-' + id;
  let choice;
  try { choice = localStorage.getItem(key); } catch { /* Browser blocks storage. */ }
  let loaded = false;

  function collect() {
    if (blocked) return;
    window[disabled] = false;
    if (loaded) return;
    loaded = true;

    // Pass only the recognized campaign labels and an origin-level referrer.
    const location = new URL(page.pathname.replace(/\/index\.html$/, '/'), page.origin);
    const qa = page.searchParams.get('geo_test') === '1';
    const source = page.searchParams.get('utm_source')?.toLowerCase();
    if (qa) {
      location.searchParams.set('utm_source', 'geo-qa');
      location.searchParams.set('utm_medium', 'test');
      location.searchParams.set('utm_campaign', 'analytics-setup');
    } else if (source === 'x' || source === 'chatgpt.com') {
      location.searchParams.set('utm_source', source);
      location.searchParams.set('utm_medium', source === 'x' ? 'social' : 'referral');
      if (source === 'x') {
        const campaign = page.searchParams.get('utm_campaign');
        const content = page.searchParams.get('utm_content');
        if (/^geo-lab-[0-9]{2}$/.test(campaign || '')) location.searchParams.set('utm_campaign', campaign);
        if (/^(original|reply|quote)(-[0-9]{1,3})?$/.test(content || '')) location.searchParams.set('utm_content', content);
      }
    }
    let referrer = '';
    try {
      const ref = new URL(document.referrer);
      if (ref.protocol === 'https:' || ref.protocol === 'http:') referrer = ref.origin + '/';
    } catch { /* Direct visit or source withheld. */ }

    window.dataLayer = window.dataLayer || [];
    function gtag() { window.dataLayer.push(arguments); }
    gtag('js', new Date());
    gtag('consent', 'default', {analytics_storage: 'granted', ad_storage: 'denied',
      ad_user_data: 'denied', ad_personalization: 'denied'});
    gtag('config', id, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_prefix: 'geolab',
      cookie_path: project,
      page_location: location.href,
      page_referrer: referrer,
      ...(qa ? {debug_mode: true} : {})
    });
    const script = document.createElement('script');
    script.async = true;
    script.referrerPolicy = 'origin';
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id);
    document.head.append(script);
  }

  const container = document.createElement('aside');
  container.setAttribute('aria-label', 'Website analytics');
  container.className = 'geo-analytics-settings';
  const css = document.createElement('style');
  css.textContent = '.geo-analytics-settings{box-sizing:border-box;max-width:80rem;margin:12px auto;padding:12px 20px;color:#21414a;font:14px/1.45 system-ui}.geo-analytics-settings a{color:#155d68}.geo-analytics-settings button{cursor:pointer;color:#17343d;background:#fff;border:1px solid #6f959e;border-radius:6px;padding:6px 10px;font:inherit}.geo-analytics-settings button:focus-visible{outline:3px solid #176a76;outline-offset:3px}.geo-analytics-settings[data-prompt]{position:fixed;bottom:12px;right:12px;left:auto;z-index:1000;max-width:min(420px,calc(100vw - 24px));margin:0;background:#f3f9fa;border:1px solid #a5c5cc;border-radius:8px;box-shadow:0 4px 16px #17343d22}.geo-analytics-settings p{margin:0 0 8px}.geo-analytics-settings button+button{margin-left:8px}@media print{.geo-analytics-settings{display:none}}';
  document.head.append(css);
  document.body.append(container);

  function preference(next) {
    choice = next;
    try { localStorage.setItem(key,next); } catch { /* Apply to this page only. */ }
    if (next === 'yes') collect();
    else {
      window[disabled] = true;
      for (const cookie of document.cookie.split(';')) {
        const name = cookie.split('=')[0].trim();
        if (/^geolab_ga(?:_[A-Z0-9]+)?$/.test(name)) {
          document.cookie = name + '=; Max-Age=0; Path=' + project + '; Secure; SameSite=Lax';
          document.cookie = name + '=; Max-Age=0; Path=' + project + '; Domain=' + page.hostname + '; Secure; SameSite=Lax';
        }
      }
    }
    show(false);
  }

  function button(label, act) {
    const control = document.createElement('button');
    control.type = 'button';
    control.textContent = label;
    control.addEventListener('click',act);
    container.append(control);
    return control;
  }

  function show(prompt) {
    container.replaceChildren();
    container.toggleAttribute('data-prompt', prompt && !blocked);
    const link = document.createElement('a');
    link.href = project + 'privacy.html';
    link.textContent = 'Analytics privacy';
    if (!prompt || blocked) {
      container.append(link);
      if (!blocked) {
        container.append(' · ');
        button('Analytics settings', () => show(true));
      }
      return;
    }
    const detail = document.createElement('p');
    detail.append('Allow optional analytics to help us understand which reports are read and how people find them? ',link);
    container.append(detail);
    button('Allow analytics', () => preference('yes'));
    button('No thanks', () => preference('no'));
  }
  show(!choice);
  if (choice === 'yes') collect();
})();
