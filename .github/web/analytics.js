(() => {
  const measurementId = "G-C8HV127V85";
  const storageKey = "tech-skills-br.analytics-consent.v1";
  const consentDuration = 180 * 24 * 60 * 60 * 1000;
  const cookiePrefix = "tsbr";
  const sitePath = "/tech-skills-br/";
  const production = window.location.hostname === "diasgarcia.github.io" &&
    window.location.pathname.startsWith(sitePath);
  const tabs = ["resumo", "skills", "areas", "vagas", "api", "sobre"];
  const resources = ["job_source", "github", "kaggle"];
  const panel = document.getElementById("analytics-consent");
  let consent = readConsent();
  let started = false;
  let activeTab = "resumo";

  window[`ga-disable-${measurementId}`] = true;

  function readConsent() {
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey));
      if (["granted", "denied"].includes(saved?.value) && saved.expiresAt > Date.now()) {
        return saved.value;
      }
    } catch { /* A escolha continua disponível mesmo sem armazenamento local. */ }
    return null;
  }

  function track(name, parameters) {
    if (!production || consent !== "granted" || !started) return;
    window.gtag("event", name, { send_to: measurementId, ...parameters });
  }

  function start() {
    if (!production || consent !== "granted" || started) return;
    started = true;
    window[`ga-disable-${measurementId}`] = false;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("consent", "default", {
      analytics_storage: "denied", ad_storage: "denied",
      ad_user_data: "denied", ad_personalization: "denied"
    });
    window.gtag("consent", "update", { analytics_storage: "granted" });
    window.gtag("js", new Date());
    let referrer = "";
    try { referrer = new URL(document.referrer).origin; } catch { /* Sem origem válida. */ }
    window.gtag("config", measurementId, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_prefix: cookiePrefix,
      cookie_path: sitePath,
      cookie_domain: window.location.hostname,
      cookie_expires: consentDuration / 1000,
      cookie_update: false,
      page_location: window.location.origin + window.location.pathname,
      page_referrer: referrer
    });
    const tag = document.createElement("script");
    tag.async = true;
    tag.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
    document.head.appendChild(tag);
    track("select_tab", { tab: activeTab });
  }

  function clearAnalyticsCookies() {
    for (const item of document.cookie.split(";")) {
      const name = item.split("=")[0].trim();
      if (!name.startsWith(`${cookiePrefix}_`)) continue;
      for (const domain of ["", `; Domain=${window.location.hostname}`]) {
        document.cookie = `${name}=; Max-Age=0; Path=${sitePath}${domain}; SameSite=Lax`;
      }
    }
  }

  function choose(value) {
    consent = value;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ value, expiresAt: Date.now() + consentDuration }));
    } catch { /* Sem persistência, a escolha vale apenas nesta página. */ }
    panel.close();
    if (value === "granted") {
      start();
    } else {
      window[`ga-disable-${measurementId}`] = true;
      clearAnalyticsCookies();
      // Remove a tag já carregada e seus eventos automáticos ao revogar.
      if (started) window.location.reload();
    }
  }

  window.siteAnalytics = {
    selectTab(tab) {
      if (!tabs.includes(tab) || tab === activeTab) return;
      activeTab = tab;
      track("select_tab", { tab });
    }
  };

  document.getElementById("analytics-accept").onclick = () => choose("granted");
  document.getElementById("analytics-reject").onclick = () => choose("denied");
  document.getElementById("analytics-preferences").onclick = () => {
    if (panel.open) panel.close();
    panel.showModal();
  };
  document.addEventListener("click", event => {
    const resource = event.target.closest?.("a[data-analytics-link]")?.getAttribute("data-analytics-link");
    if (resources.includes(resource)) track("click_resource", { resource });
  });
  window.addEventListener("storage", event => {
    if (event.key !== storageKey && event.key !== null) return;
    consent = readConsent();
    if (consent === "granted") start();
    else if (started) {
      window[`ga-disable-${measurementId}`] = true;
      clearAnalyticsCookies();
      window.location.reload();
    } else if (!consent && !panel.open) panel.show();
    if (consent && panel.open) panel.close();
  });

  if (!production) document.getElementById("analytics-local-note").hidden = false;
  if (consent === "granted") start();
  else if (!consent) panel.show();
})();
