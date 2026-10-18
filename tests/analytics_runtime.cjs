const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../.github/web/analytics.js"), "utf8");
const key = "tech-skills-br.analytics-consent.v1";
const id = "G-C8HV127V85";
const saved = value => JSON.stringify({ value, expiresAt: Date.now() + 100000 });

function runtime({ stored = null, hostname = "diasgarcia.github.io", pathname = "/tech-skills-br/", blockedStorage = false } = {}) {
  const elements = new Map();
  const listeners = {};
  const storage = new Map(stored ? [[key, stored]] : []);
  const scripts = [];
  const cookieChanges = [];
  let reloads = 0;
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      hidden: true, open: false, modal: false,
      close() { this.open = false; },
      show() { this.open = true; this.modal = false; },
      showModal() { this.open = true; this.modal = true; }
    });
    return elements.get(id);
  };
  const document = {
    referrer: "https://example.test/path?email=private@example.test",
    getElementById: element,
    createElement: () => ({}),
    head: { appendChild: script => scripts.push(script) },
    addEventListener: (name, handler) => { listeners[name] = handler; }
  };
  Object.defineProperty(document, "cookie", {
    get: () => "tsbr_ga=ours; tsbr_ga_C8HV127V85=ours; _ga=portfolio; another=value",
    set: value => cookieChanges.push(value)
  });
  const window = {
    location: { hostname, pathname, origin: `https://${hostname}`, reload() { reloads += 1; } },
    localStorage: {
      getItem(name) { if (blockedStorage) throw new Error("Storage bloqueado"); return storage.get(name) ?? null; },
      setItem(name, value) { if (blockedStorage) throw new Error("Storage bloqueado"); storage.set(name, value); }
    },
    addEventListener: (name, handler) => { listeners[name] = handler; }
  };
  const sandbox = { URL, window, document };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  const commands = () => Array.from(window.dataLayer || [], args => Array.from(args));
  return {
    window, scripts, storage, cookieChanges, element, commands, listeners,
    accept: () => element("analytics-accept").onclick(),
    reject: () => element("analytics-reject").onclick(),
    reloads: () => reloads
  };
}

test("antes de aceitar não carrega a tag nem registra ações", () => {
  const app = runtime();

  app.window.siteAnalytics.selectTab("vagas");

  assert.equal(app.scripts.length, 0);
  assert.equal(app.commands().length, 0);
  assert.equal(app.window[`ga-disable-${id}`], true);
  assert.equal(app.element("analytics-consent").open, true);
});

test("aceitar carrega uma tag com publicidade negada e dados limitados", () => {
  const app = runtime();

  app.window.siteAnalytics.selectTab("vagas");
  app.accept();
  app.accept();
  const commands = app.commands();
  const config = commands.find(args => args[0] === "config");

  assert.equal(app.scripts.length, 1);
  assert.equal(app.scripts[0].src, `https://www.googletagmanager.com/gtag/js?id=${id}`);
  assert.equal(app.scripts[0].async, true);
  assert.equal(app.element("analytics-consent").open, false);
  assert.equal(JSON.parse(app.storage.get(key)).value, "granted");
  assert.equal(commands[0][2].analytics_storage, "denied");
  assert.equal(commands[0][2].ad_storage, "denied");
  assert.equal(commands[0][2].ad_user_data, "denied");
  assert.equal(commands[0][2].ad_personalization, "denied");
  assert.equal(commands[1][2].analytics_storage, "granted");
  assert.equal(config[1], id);
  assert.equal(config[2].allow_google_signals, false);
  assert.equal(config[2].allow_ad_personalization_signals, false);
  assert.equal(config[2].page_location, "https://diasgarcia.github.io/tech-skills-br/");
  assert.equal(config[2].page_referrer, "https://example.test");
  assert.equal(config[2].cookie_prefix, "tsbr");
  assert.equal(config[2].cookie_path, "/tech-skills-br/");
  assert.equal(config[2].cookie_update, false);
  assert.equal(commands.filter(args => args[0] === "config").length, 1);
  assert.equal(commands.find(args => args[0] === "event")[2].tab, "vagas");
});

test("recusar mantém o site sem tag e permite mudar depois", () => {
  const app = runtime();

  app.reject();
  app.element("analytics-preferences").onclick();
  const reopened = app.element("analytics-consent").modal;
  app.accept();

  assert.equal(reopened, true);
  assert.equal(app.scripts.length, 1);
  assert.equal(app.reloads(), 0);
});

test("escolha salva é respeitada", () => {
  const granted = runtime({ stored: saved("granted") });
  const denied = runtime({ stored: saved("denied") });

  assert.equal(granted.scripts.length, 1);
  assert.equal(denied.scripts.length, 0);
  assert.equal(granted.element("analytics-consent").open, false);
  assert.equal(denied.element("analytics-consent").open, false);
});

test("escolha inválida ou expirada não ativa medição", () => {
  for (const stored of ["broken", "null", saved("anything"), JSON.stringify({ value: "granted", expiresAt: 1 })]) {
    const app = runtime({ stored });

    assert.equal(app.scripts.length, 0);
    assert.equal(app.element("analytics-consent").open, true);
  }
});

test("armazenamento bloqueado não impede aceitar ou recusar", () => {
  const app = runtime({ blockedStorage: true });

  app.accept();
  app.reject();

  assert.equal(app.scripts.length, 1);
  assert.equal(app.reloads(), 1);
});

test("localhost e outros caminhos não enviam medição nem com aceite salvo", () => {
  for (const options of [{ hostname: "127.0.0.1" }, { hostname: "localhost" }, { pathname: "/portfolio/" }]) {
    const app = runtime({ ...options, stored: saved("granted") });

    app.window.siteAnalytics.selectTab("vagas");

    assert.equal(app.scripts.length, 0);
    assert.equal(app.commands().length, 0);
    assert.equal(app.element("analytics-local-note").hidden, false);
  }
});

test("revogar bloqueia eventos e remove apenas cookies do projeto", () => {
  const app = runtime({ stored: saved("granted") });
  const count = app.commands().length;

  app.reject();
  app.window.siteAnalytics.selectTab("vagas");

  assert.equal(app.commands().length, count);
  assert.equal(app.reloads(), 1);
  assert.equal(app.window[`ga-disable-${id}`], true);
  assert.equal(JSON.parse(app.storage.get(key)).value, "denied");
  assert.equal(app.cookieChanges.length, 4);
  assert.ok(app.cookieChanges.every(cookie => cookie.startsWith("tsbr_") && cookie.includes("Max-Age=0")));
  assert.ok(app.cookieChanges.every(cookie => cookie.includes("Path=/tech-skills-br/")));
});

test("revogação em outra aba interrompe a medição desta aba", () => {
  const app = runtime({ stored: saved("granted") });
  app.storage.set(key, saved("denied"));

  app.listeners.storage({ key });

  assert.equal(app.reloads(), 1);
  assert.equal(app.window[`ga-disable-${id}`], true);
});

test("eventos aceitam só nomes de abas e destinos previstos", () => {
  const app = runtime({ stored: saved("granted") });
  const click = resource => app.listeners.click({ target: { closest: () => ({ getAttribute: () => resource }) } });

  app.window.siteAnalytics.selectTab("vagas");
  app.window.siteAnalytics.selectTab("vagas");
  app.window.siteAnalytics.selectTab("email@example.test");
  click("job_source");
  click("github");
  click("kaggle");
  click("email@example.test");
  const events = app.commands().filter(args => args[0] === "event");

  assert.deepEqual(events.map(args => args[1]), ["select_tab", "select_tab", "click_resource", "click_resource", "click_resource"]);
  assert.ok(events.every(args => args[2].send_to === id));
  assert.ok(!JSON.stringify(events).includes("email@example.test"));
});
