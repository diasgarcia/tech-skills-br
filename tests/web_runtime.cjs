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
    this.open = false;
    this.attributes = {};
    this._text = "";
  }
  set innerHTML(_) { throw new Error("Não interpretar conteúdo como HTML"); }
  set textContent(text) { this._text = String(text); this.childNodes = []; }
  get textContent() { return this._text + this.childNodes.map(node => node.textContent).join(""); }
  set innerText(text) { this.textContent = text; }
  get innerText() { return this.textContent; }
  appendChild(node) { assert.equal(node.nodeType, 1); this.childNodes.push(node); return node; }
  replaceChildren(...nodes) { this._text = ""; this.childNodes = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  show() { this.open = true; this.modal = false; }
  showModal() { this.open = true; this.modal = true; }
  close() { this.open = false; if (this.onclose) this.onclose(); }
  getBoundingClientRect() { return { top: 100, bottom: 130, left: 10, right: 440, width: 430, height: 430 }; }
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
    setTimeout,
    clearTimeout,
    fetch,
    console: { error() {} },
    window: { addEventListener() {}, innerHeight: 900, innerWidth: 1200, matchMedia: () => ({ matches: true }) },
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

test("KPI mostra a presença entre áreas, não o total de citações", () => {
  const app = runtime();
  app.sandbox.fixture = { nome: "Inglês", areas: 18, total_areas: 18, media_percentual: 22 };

  app.run("resumoData = { habilidade_entre_areas: fixture }; tecnologiasData = [{ nome: 'Hardware', vagas: 2218 }]; initKPIs()");

  assert.equal(app.get("kpi-top-skill").textContent, "Inglês");
  assert.equal(app.get("kpi-top-skill-count").textContent, "Presença média por área: 22,0%");
  assert.ok(app.get("kpi-top-skill-count").title.includes("18 de 18 áreas"));
  assert.ok(app.get("kpi-top-skill-count").title.includes("Não é o percentual da base inteira"));
});

test("presença média mantém zero com uma casa decimal", () => {
  const app = runtime();
  app.sandbox.fixture = { nome: "Skill", areas: 1, total_areas: 18, media_percentual: 0 };

  app.run("resumoData = { habilidade_entre_areas: fixture }; initKPIs()");

  assert.equal(app.get("kpi-top-skill-count").textContent, "Presença média por área: 0,0%");
});

test("KPI sem habilidades limpa dados e explicação anteriores", () => {
  const app = runtime();
  app.run("resumoData = { habilidade_entre_areas: { nome: 'Inglês', areas: 1, total_areas: 2, media_percentual: 10 } }; initKPIs()");

  app.run("resumoData = { habilidade_entre_areas: null }; initKPIs()");

  assert.equal(app.get("kpi-top-skill").textContent, "--");
  assert.equal(app.get("kpi-top-skill-count").textContent, "--");
  assert.equal(app.get("kpi-top-skill-count").title, "");
});

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
  assert.equal(links.length, 1);
  const directLink = links.find(link => link.className === "job-direct-link");
  assert.equal(directLink.attributes["aria-label"], "Abrir vaga na fonte");
  assert.equal(directLink.attributes["data-analytics-link"], "job_source");
  assert.equal(directLink.onclick, undefined);
  assert.equal(rows[1].childNodes.at(-1).className, "job-link-col");
  assert.equal(rows[1].childNodes.at(-1).childNodes[0], directLink);
  assert.ok(links.every(link => link.href.startsWith("https://example.test/")));
  assert.ok(links.every(link => link.rel === "noopener noreferrer"));
  assert.ok(links.every(link => !link.onmouseover));
});

test("URLs aceitas são absolutas HTTP(S), inclusive nos detalhes", () => {
  const app = runtime();
  for (const url of ["javascript:alert(1)", "data:text/html,test", "//example.test", "/vaga", "https://", "file:///tmp/test", "java\nscript:alert(1)"]) {
    app.sandbox.url = url;
    assert.equal(app.run("jobLink(url, 'Vaga')"), null, url);
  }
  app.sandbox.url = " HTTPS://example.test/vaga ";
  assert.equal(app.run("jobLink(url, 'Vaga').href"), "https://example.test/vaga");
});


test("local nacional preserva Brasil e remoto não duplica a modalidade", () => {
  const app = runtime();
  app.sandbox.fixture = [
    { titulo: "Nacional", localidade: "Brasil", polo: "Nacional", modalidade: "Remoto", data_publicacao: today() },
    { titulo: "Sem cidade", localidade: "Remoto", polo: "Remoto", modalidade: "Remoto", data_publicacao: today() },
    { titulo: "Cidade", localidade: "Ourinhos, SP", polo: "Interior Paulista Ocidental", modalidade: "Remoto", data_publicacao: today() },
  ];

  app.run("vagasData = fixture; renderVagasTable()");
  const places = app.get("#table-vagas tbody").childNodes.map(row =>
    walk(row).filter(node => node.className === "job-place").map(node => node.textContent)
  );

  assert.deepEqual(places, [["Brasil"], [], ["Ourinhos, SP"]]);
});

test("hover mostra dados literais sem bloquear a página; clique abre modal", () => {
  const app = runtime();
  const injected = '<img src=x onerror="alert(1)">';
  app.sandbox.fixture = {
    titulo: injected, empresa: "Empresa", area: "Backend", senioridade: "Júnior",
    localidade: "São Paulo, SP", modalidade: "Remoto", regiao: "Sudeste", polo: "São Paulo",
    fonte: "jobbol", tecnologias: [injected, "Python"], url: "https://example.test/vaga",
    data_publicacao: today()
  };
  app.run("vagasData = [fixture]; renderVagasTable()");
  const trigger = walk(app.get("#table-vagas tbody")).find(node => node.className === "job-title");

  trigger.onpointerenter({ pointerType: "mouse" });
  const hoverOpened = app.get("job-details").open && !app.get("job-details").modal;
  const hoverLeft = parseFloat(app.get("job-details").style.left);
  trigger.onclick();
  const modalOpened = app.get("job-details").modal;
  app.run("closeJobDetails()");

  assert.equal(hoverOpened, true);
  assert.ok(hoverLeft >= trigger.getBoundingClientRect().right + 8);
  assert.equal(modalOpened, true);
  assert.equal(app.get("job-details-title").textContent, injected);
  assert.ok(app.get("job-details-fields").textContent.includes("Sudeste / São Paulo"));
  assert.ok(app.get("job-details-skills").textContent.includes("Python"));
  assert.equal(walk(app.get("job-details-skills")).filter(node => node.tagName === "IMG").length, 0);
  assert.equal(app.get("job-details-link").childNodes[0].rel, "noopener noreferrer");
  assert.equal(app.get("job-details").open, false);
  assert.equal(trigger.attributes["aria-expanded"], "false");
});

test("sem espaço nas laterais o hover fica fora dos limites do título", () => {
  const app = runtime();
  app.sandbox.window.innerWidth = 500;
  app.sandbox.window.innerHeight = 500;
  app.sandbox.fixture = { titulo: "Vaga", data_publicacao: today() };
  app.run("vagasData = [fixture]; renderVagasTable()");
  const trigger = walk(app.get("#table-vagas tbody")).find(node => node.className === "job-title");

  trigger.onpointerenter({ pointerType: "mouse" });

  assert.ok(parseFloat(app.get("job-details").style.top) > trigger.getBoundingClientRect().bottom);
  assert.ok(parseFloat(app.get("job-details").style.maxHeight) <= 350);
});

test("toque não abre hover; detalhes vazios e URL insegura têm fallback", () => {
  const app = runtime();
  app.sandbox.fixture = { titulo: "Vaga", url: "javascript:alert(1)", data_publicacao: today() };
  app.run("vagasData = [fixture]; renderVagasTable()");
  const trigger = walk(app.get("#table-vagas tbody")).find(node => node.className === "job-title");

  trigger.onpointerenter({ pointerType: "touch" });
  const openedOnTouchHover = app.get("job-details").open;
  trigger.onclick();

  assert.equal(openedOnTouchHover, false);
  assert.equal(app.get("job-details").modal, true);
  assert.ok(app.get("job-details-fields").textContent.includes("Não informado"));
  assert.ok(app.get("job-details-skills").textContent.includes("Nenhuma habilidade"));
  assert.equal(walk(app.get("job-details-link")).filter(node => node.tagName === "A").length, 0);
});

test("filtrar fecha os detalhes para não manter anúncio fora da lista", () => {
  const app = runtime();
  app.sandbox.fixture = { titulo: "Vaga", data_publicacao: today() };
  app.run("vagasData = [fixture]; renderVagasTable()");
  const trigger = walk(app.get("#table-vagas tbody")).find(node => node.className === "job-title");
  trigger.onclick();

  app.run("renderVagasTable()");

  assert.equal(app.get("job-details").open, false);
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
