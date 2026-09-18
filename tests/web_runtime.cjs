// DOM de teste deliberadamente sem parser HTML. Qualquer tentativa de usar
// innerHTML falha; a árvore permite inspecionar textos, links e estilos reais
// produzidos pelo script. Não substitui teste visual em navegador.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.nodeType = 1;
    this.childNodes = [];
    this.style = {};
    this.className = "";
    this.value = "";
    this.hidden = false;
    this._text = "";
  }
  set innerHTML(_) { throw new Error("Não interpretar conteúdo como HTML"); }
  set textContent(text) { this._text = String(text); this.childNodes = []; }
  get textContent() { return this._text + this.childNodes.map(node => node.textContent).join(""); }
  set innerText(text) { this.textContent = text; }
  get innerText() { return this.textContent; }
  appendChild(node) { assert.equal(node.nodeType, 1); this.childNodes.push(node); return node; }
  replaceChildren(...nodes) { this._text = ""; this.childNodes = nodes; }
  getBoundingClientRect() { return { top: 800 }; }
}

const source = fs.readFileSync(path.join(__dirname, "../.github/web/app.js"), "utf8");
const walk = node => [node, ...node.childNodes.flatMap(walk)];

function runtime(fetch = () => { throw new Error("Rede não autorizada no teste"); }) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, new Element("div"));
    return elements.get(id);
  };
  const sandbox = {
    URL,
    fetch,
    console: { error() {} },
    window: { addEventListener() {}, innerHeight: 900 },
    document: {
      createElement: tag => new Element(tag),
      getElementById: get,
      querySelector: get,
      querySelectorAll: () => [],
      addEventListener() {},
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return { get, sandbox, run: code => vm.runInContext(code, sandbox) };
}

function today() {
  const date = new Date();
  return `${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`;
}

test("anúncios são texto literal; links inseguros não viram âncoras", () => {
  const app = runtime();
  const injected = '<img src=x onerror="alert(1)">';
  app.sandbox.fixture = [
    { titulo: injected, empresa: '<script>alert(2)</script>', area: injected,
      localidade: injected, modalidade: "Remoto", url: "javascript:alert(1)", data_publicacao: today() },
    { titulo: 'Python "Júnior"', empresa: "Empresa", area: "Backend", localidade: "São Paulo",
      modalidade: "Híbrido", url: 'https://example.test/vaga?x=" onmouseover="alert(3)', data_publicacao: today() },
  ];

  app.run("vagasData = fixture; renderVagasTable()");
  const rows = app.get("#table-vagas tbody").childNodes;
  const links = walk(rows[1]).filter(node => node.tagName === "A");

  assert.equal(rows.length, 2);
  assert.ok(rows[0].textContent.includes(injected));
  assert.equal(walk(rows[0]).filter(node => ["IMG", "SCRIPT", "A"].includes(node.tagName)).length, 0);
  assert.equal(links.length, 2);
  assert.ok(links.every(link => link.href.startsWith("https://example.test/")));
  assert.ok(links.every(link => link.rel === "noopener noreferrer"));
  assert.ok(links.every(link => !link.onmouseover));
});

test("URLs aceitas são absolutas HTTP(S), inclusive no título mobile", () => {
  const app = runtime();
  for (const url of ["javascript:alert(1)", "data:text/html,test", "//example.test", "/vaga", "https://", "file:///tmp/test", "java\nscript:alert(1)"]) {
    app.sandbox.url = url;
    assert.equal(app.run("jobLink(url, 'Vaga')"), null, url);
  }
  app.sandbox.url = " HTTPS://example.test/vaga ";
  assert.equal(app.run("jobLink(url, 'Vaga').href"), "https://example.test/vaga");
});

test("resumos, ranking, pills e detalhes não interpretam os dados como HTML ou CSS", () => {
  const app = runtime();
  const unsafe = '<svg onload="alert(1)">';
  app.sandbox.fixture = { nome: unsafe, grupo: unsafe, vagas: 2, percentual: '50%; color: red', percentual_total: '50%; color: red', posicao: 1 };
  app.sandbox.unsafe = unsafe;

  app.run(`
    areasData = [{ area: unsafe, vagas: 2, percentual: 200 }];
    tecnologiasData = [fixture];
    resumoData = { regioes: [{ regiao: unsafe, vagas: 2, percentual: -5 }],
      modalidades: [{ modalidade: unsafe, vagas: 2, percentual: 100 }],
      skills_by_area: { [unsafe]: { total_vagas: 2, vagas_com_tech: 2, skills: [fixture] } } };
    renderSummaryTables(); renderSkillsTable(); initAreaPills();
  `);
  const containers = ["#table-areas-summary tbody", "#table-regioes-summary tbody", "#table-modalidades-summary tbody", "#table-skills tbody", "#table-area-skills tbody", "area-pills-container"];

  for (const id of containers) {
    assert.ok(app.get(id).textContent.includes(unsafe), id);
    assert.equal(walk(app.get(id)).filter(node => node.tagName === "SVG").length, 0);
  }
  assert.equal(walk(app.get("#table-areas-summary tbody")).find(node => node.className === "bar-fill").style.width, "100%");
  assert.equal(walk(app.get("#table-regioes-summary tbody")).find(node => node.className === "bar-fill").style.width, "0%");
  assert.equal(walk(app.get("#table-skills tbody")).find(node => node.className === "bar-fill").style.width, "0%");
});

test("busca continua combinando tecnologia, área e modalidade", () => {
  const app = runtime();
  app.sandbox.fixture = [
    { titulo: "Desenvolvedor", empresa: "Empresa", area: "Backend", tecnologias: ["Python"], modalidade: "Remoto", data_publicacao: today() },
    { titulo: "Desenvolvedor", empresa: "Empresa", area: "Frontend", tecnologias: ["React"], modalidade: "Remoto", data_publicacao: today() },
  ];
  app.get("search-vagas").value = "python backend";
  app.get("filter-modalidade").value = "Remoto";

  app.run("vagasData = fixture; renderVagasTable()");

  assert.equal(app.get("#table-vagas tbody").childNodes.length, 1);
  assert.ok(app.get("#table-vagas tbody").textContent.includes("Backend"));
});

test("prefixo compartilhado por empresa e cidade pesquisa os dois campos", () => {
  const app = runtime();
  app.sandbox.fixture = [
    { titulo: "Analista", empresa: "Americanas", localidade: "Rio de Janeiro, RJ", data_publicacao: today() },
    { titulo: "Suporte", empresa: "Empresa Local", localidade: "Americana, SP", data_publicacao: today() },
    { titulo: "Desenvolvedor", empresa: "Outra Empresa", localidade: "São Paulo, SP", data_publicacao: today() },
  ];
  app.get("search-vagas").value = "amer";

  app.run("vagasData = fixture; renderVagasTable()");

  const results = app.get("#table-vagas tbody");
  assert.equal(results.childNodes.length, 2);
  assert.ok(results.textContent.includes("Americanas"));
  assert.ok(results.textContent.includes("Americana, SP"));
});

test("falha HTTP mostra recuperação e não tenta interpretar resposta de erro", async () => {
  let failed = true;
  let parsedError = false;
  const app = runtime(async path => {
    if (failed) return { ok: false, status: 503, json() { parsedError = true; } };
    return { ok: true, json: async () => path.endsWith("resumo.json") ? { metadados: {}, skills_by_area: {} } : [] };
  });

  await app.run("loadData()");
  const failureVisible = !app.get("data-status").hidden;
  const retryVisible = !app.get("data-retry").hidden;
  failed = false;
  await app.run("loadData()");

  assert.equal(parsedError, false);
  assert.equal(failureVisible, true);
  assert.equal(retryVisible, true);
  assert.equal(app.get("data-status").hidden, true);
  assert.equal(app.get("#table-vagas tbody").childNodes.length, 0);
});

test("JSON inválido oferece tentativa novamente", async () => {
  const app = runtime(async () => ({ ok: true, json: async () => { throw new SyntaxError("JSON inválido"); } }));

  await app.run("loadData()");

  assert.equal(app.get("data-status").hidden, false);
  assert.equal(app.get("data-retry").hidden, false);
  assert.match(app.get("data-status-message").textContent, /Não foi possível/);
});

test("carregamento rejeita estrutura inválida sem atribuir dados parciais", async () => {
  const app = runtime(async () => ({ ok: true, json: async () => ({ inesperado: true }) }));

  await app.run("loadData()");

  assert.equal(app.run("resumoData"), null);
  assert.equal(app.get("data-retry").hidden, false);
});
