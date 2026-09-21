let resumoData = null;
let tecnologiasData = [];
let areasData = [];
let vagasData = [];
let currentArea = null;
let dataLoading = false;

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Falha ao carregar ${path}: HTTP ${response.status}`);
  return response.json();
}

async function loadData() {
  if (dataLoading) return;
  dataLoading = true;
  const status = document.getElementById("data-status");
  const message = document.getElementById("data-status-message");
  const retry = document.getElementById("data-retry");
  status.hidden = false;
  message.textContent = "Carregando dados...";
  retry.hidden = true;
  try {
    const [resResumo, resTech, resAreas, resVagas] = await Promise.all([
      fetchJson("api/resumo.json"),
      fetchJson("api/tecnologias.json"),
      fetchJson("api/areas.json"),
      fetchJson("api/vagas.json")
    ]);
    if (!resResumo || typeof resResumo !== "object" || Array.isArray(resResumo) ||
        ![resTech, resAreas, resVagas].every(Array.isArray)) {
      throw new Error("Formato inválido nos dados da API estática");
    }

    resumoData = resResumo;
    tecnologiasData = resTech;
    areasData = resAreas;
    vagasData = resVagas;
    currentArea = areasData.length ? areasData[0].area : null;

    initKPIs();
    initFreshness();
    renderSummaryTables();
    renderSkillsTable();
    initAreaPills();
    renderVagasTable();
    status.hidden = true;
    ajustaAlturaScrollTables();
  } catch (err) {
    console.error("Erro ao carregar dados da API estática:", err);
    message.textContent = "Não foi possível carregar os dados. Tente novamente.";
    retry.hidden = false;
  } finally {
    dataLoading = false;
  }
}

function initFreshness() {
  const node = document.getElementById("footer-freshness");
  if (!node) return;
  const meta = resumoData?.metadados || {};
  if (!meta.ultima_coleta) return;

  const collectedAt = new Date(meta.ultima_coleta);
  if (Number.isNaN(collectedAt.getTime())) return;
  const label = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(collectedAt);
  const stale = meta.estado_frescor === "atrasado";
  node.textContent = stale ? `Dados atrasados: ${label}` : `Dados: ${label}`;
  node.classList.toggle("footer-stale", stale);
  node.title = stale
    ? "A última coleta completa válida ocorreu há mais de 24 horas."
    : "Data e hora da última coleta completa válida.";
}

document.addEventListener("DOMContentLoaded", loadData);

function element(tag, text = null, className = "", styles = {}) {
  const node = document.createElement(tag);
  if (text !== null) node.textContent = String(text);
  node.className = className;
  Object.assign(node.style, styles);
  return node;
}

function cell(row, content, className = "", styles = {}) {
  const td = element("td", null, className, styles);
  if (content && typeof content === "object" && content.nodeType) td.appendChild(content);
  else td.textContent = content == null ? "Não informado" : String(content);
  row.appendChild(td);
  return td;
}

function bar(percent, color = "var(--accent)") {
  const value = Number(percent);
  const width = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
  const wrap = element("div", null, "bar-wrap");
  wrap.appendChild(element("div", null, "bar-fill", { width: `${width}%`, background: color }));
  return wrap;
}

function jobLink(url, text, styles = {}) {
  if (typeof url !== "string" || !/^https?:\/\//i.test(url.trim())) return null;
  let parsed;
  try { parsed = new URL(url); } catch { return null; }
  if (!["http:", "https:"].includes(parsed.protocol)) return null;
  const link = element("a", text, "", styles);
  link.href = parsed.href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.title = "Abrir vaga";
  return link;
}


function setTab(tabId) {
  const isTableTab = ["skills", "areas", "vagas"].includes(tabId);
  document.documentElement.classList.toggle("table-tab-active", isTableTab);
  document.body.classList.toggle("table-tab-active", isTableTab);
  if (isTableTab) window.scrollTo(0, 0);

  document.querySelectorAll(".tab-section").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(btn => btn.classList.remove("active"));

  const target = document.getElementById("tab-" + tabId);
  if (target) target.classList.add("active");

  const btnIndex = { resumo: 0, skills: 1, areas: 2, vagas: 3, api: 4, sobre: 5 }[tabId];
  const btns = document.querySelectorAll(".nav-btn");
  if (btns[btnIndex]) {
    btns[btnIndex].classList.add("active");
    if (window.innerWidth <= 768) {
      btns[btnIndex].scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    }
  }

  ajustaAlturaScrollTables();
}

function ajustaAlturaScrollTables() {
  const footer = document.querySelector("footer");
  const limiteInferior = footer ? footer.getBoundingClientRect().top : window.innerHeight;
  document.querySelectorAll(".scroll-table").forEach(el => {
    if (!el.offsetParent) return; // aba escondida
    const topo = el.getBoundingClientRect().top;
    const card = el.closest(".card");
    const estiloCard = card ? getComputedStyle(card) : null;
    const espacoInferior = estiloCard
      ? parseFloat(estiloCard.paddingBottom) + parseFloat(estiloCard.borderBottomWidth)
      : 0;
    const altura = limiteInferior - topo - espacoInferior;
    el.style.maxHeight = Math.max(200, altura) + "px";
  });
}
window.addEventListener("resize", ajustaAlturaScrollTables);

function initKPIs() {
  const meta = resumoData.metadados || {};
  const total = meta.total_vagas || 0;

  document.getElementById("kpi-total").textContent = total.toLocaleString("pt-BR");
  document.getElementById("kpi-periodo").textContent = meta.periodo ? `Período: ${meta.periodo}` : "";
  document.getElementById("kpi-empresas").textContent = (meta.total_empresas || 0).toLocaleString("pt-BR");

  // Top 1 Tecnologia Dinâmica (ordenação vinda da base)
  const topTech = (tecnologiasData && tecnologiasData.length > 0) ? tecnologiasData[0] : null;
  if (topTech) {
    document.getElementById("kpi-top-skill").textContent = topTech.nome;
    document.getElementById("kpi-top-skill-count").textContent = `${topTech.vagas} citações (${topTech.percentual_total}% da base)`;
  } else {
    document.getElementById("kpi-top-skill").textContent = "--";
    document.getElementById("kpi-top-skill-count").textContent = "--";
  }

  // Modalidade Dominante Dinâmica (pega a maior da lista)
  const modalidades = resumoData.modalidades || [];
  if (modalidades.length > 0) {
    const topMod = modalidades[0];
    document.getElementById("kpi-top-mod-title").textContent = `Modalidade: ${topMod.modalidade}`;
    document.getElementById("kpi-top-mod-value").textContent = `${topMod.percentual}%`;
    document.getElementById("kpi-top-mod-sub").textContent = `${topMod.vagas.toLocaleString("pt-BR")} vagas nesta modalidade`;
  } else {
    document.getElementById("kpi-top-mod-title").textContent = "Modalidade Dominante";
    document.getElementById("kpi-top-mod-value").textContent = "--";
    document.getElementById("kpi-top-mod-sub").textContent = "--";
  }
}

function renderSummaryTables() {
  const summaries = [
    ["areas", (areasData || []).slice(0, 13), "area", "var(--accent)"],
    ["regioes", resumoData?.regioes || [], "regiao", "var(--green)"],
    ["modalidades", resumoData?.modalidades || [], "modalidade", "var(--amber)"]
  ];
  summaries.forEach(([name, items, label, color]) => {
    const tbody = document.querySelector(`#table-${name}-summary tbody`);
    tbody.replaceChildren();
    items.forEach(item => {
      const tr = element("tr");
      const title = item[label] ?? "Não informado";
      cell(tr, name === "areas" ? element("strong", title) : title);
      cell(tr, item.vagas, "", { textAlign: "center" });
      cell(tr, `${item.percentual}%`, "", { textAlign: "right" });
      cell(tr, bar(item.percentual, color), "hide-mobile");
      tbody.appendChild(tr);
    });
  });
}

function appendSkillRow(tbody, skill, rank, percent, color) {
  const tr = element("tr");
  cell(tr, rank, "rank-col", { color: "var(--text-muted)" });
  cell(tr, element("strong", skill.nome, "", { color: "var(--text-bright)" }), "technology-col");
  cell(tr, element("span", skill.grupo, "badge"), "hide-mobile", { textAlign: "center" });
  cell(tr, skill.vagas, "", { textAlign: "center" });
  cell(tr, element("strong", `${percent}%`), "", { textAlign: "right" });
  cell(tr, bar(percent, color), "hide-mobile proportion-col");
  tbody.appendChild(tr);
}

function renderSkillsTable() {
  const query = (document.getElementById("search-skills").value || "").toLowerCase().trim();
  const tbody = document.querySelector("#table-skills tbody");
  tbody.replaceChildren();

  let items = tecnologiasData || [];
  if (query) {
    items = items.filter(t => String(t.nome || "").toLowerCase().includes(query) || String(t.grupo || "").toLowerCase().includes(query));
  }

  items.forEach(t => {
    appendSkillRow(tbody, t, t.posicao, t.percentual_total, "var(--accent)");
  });
}

function initAreaPills() {
  if (!currentArea && areasData && areasData.length > 0) {
    currentArea = areasData[0].area;
  }
  const container = document.getElementById("area-pills-container");

  container.replaceChildren();

  areasData.forEach(a => {
    const span = document.createElement("span");
    span.className = `pill ${a.area === currentArea ? 'active' : ''}`;
    span.textContent = `${a.area} (${a.vagas})`;
    span.onclick = () => selectArea(a.area);
    container.appendChild(span);
  });

  renderAreaDetail();
}

function selectArea(areaName) {
  currentArea = areaName;
  initAreaPills();
}

function renderAreaDetail() {
  const areaInfo = resumoData?.skills_by_area?.[currentArea] || { total_vagas: 0, skills: [] };
  document.getElementById("area-detail-title").textContent = currentArea ? `Habilidades mais citadas em ${currentArea}` : "Habilidades por área";
  const baseSkills = areaInfo.skills?.length ? (areaInfo.vagas_com_tech || 0) : 0;
  document.getElementById("area-detail-subtitle").textContent = `${areaInfo.total_vagas} anúncios na área. Frequência calculada sobre ${baseSkills} com ao menos uma habilidade identificada.`;

  const tbody = document.querySelector("#table-area-skills tbody");
  tbody.replaceChildren();

  if (!areaInfo.skills || areaInfo.skills.length === 0) {
    const tr = document.createElement("tr");
    const message = cell(tr, "Nenhuma habilidade foi identificada nos textos disponíveis desta área. Isso pode ocorrer por texto incompleto ou termos fora do vocabulário.", "", { textAlign: "center", color: "var(--text-muted)", padding: "18px" });
    message.colSpan = 6;
    tbody.appendChild(tr);
    return;
  }

  (areaInfo.skills || []).forEach((s, idx) => {

    appendSkillRow(tbody, s, idx + 1, s.percentual, "var(--purple)");
  });
}

function parsePtBrDate(str) {
  if (!str) return null;
  const parts = str.split("/");
  if (parts.length !== 3) return null;
  return new Date(parseInt(parts[2], 10), parseInt(parts[1], 10) - 1, parseInt(parts[0], 10));
}

function getDaysAgo(dateStr) {
  const d = parsePtBrDate(dateStr);
  if (!d) return 999;
  const now = new Date();
  const diffTime = now - d;
  return Math.max(0, Math.floor(diffTime / (1000 * 60 * 60 * 24)));
}

function normalizeSearchText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

// Termos curtos que quase sempre casam com qualquer campo e so
// atrapalham o E logico entre os tokens da busca.
const SEARCH_STOPWORDS = new Set([
  "a", "o", "e", "de", "da", "do", "das", "dos",
  "em", "na", "no", "nas", "nos", "para", "com", "um", "uma", "por"
]);

// Prefixo no inicio de palavra: "suport" acha "suporte", "playw"
// acha "playwright" etc. Permite buscar enquanto se digita.
function matchWithBoundaryPrefix(haystack, needle) {
  if (!needle) return false;
  let idx = haystack.indexOf(needle);
  while (idx !== -1) {
    const before = idx === 0 ? "" : haystack[idx - 1];
    if (!/[a-z0-9]/.test(before)) return true;
    idx = haystack.indexOf(needle, idx + 1);
  }
  return false;
}

function renderVagasTable() {
  const rawQuery = normalizeSearchText(document.getElementById("search-vagas").value).trim();
  const modFilter = (document.getElementById("filter-modalidade").value || "").trim();
  const tbody = document.querySelector("#table-vagas tbody");
  tbody.replaceChildren();

  // Exibe apenas vagas recentes publicadas nos últimos 30 dias
  let items = (vagasData || []).filter(v => getDaysAgo(v.data_publicacao) <= 30);

  if (modFilter) {
    items = items.filter(v => v.modalidade === modFilter);
  }
  if (rawQuery) {
    const keywords = rawQuery.split(/\s+/)
      .filter(token => token && !SEARCH_STOPWORDS.has(token));

    items = items.filter(v => {
      const tecnologias = Array.isArray(v.tecnologias) ? v.tecnologias : [v.tecnologias];
      const searchableFields = [
        v.titulo, v.empresa, v.area, v.modalidade, v.fonte,
        v.localidade, v.polo, v.regiao, ...tecnologias
      ];
      // Alem do prefixo de palavra, tenta casar ignorando espacos:
      // "startbet" encontra "Start Bet", "javascript" encontra
      // "Java Script".
      const semEspacos = s => s.replace(/\s+/g, "");
      return keywords.every(kw =>
        searchableFields.some(value => {
          const norm = normalizeSearchText(value);
          return matchWithBoundaryPrefix(norm, kw) ||
            matchWithBoundaryPrefix(semEspacos(norm), semEspacos(kw));
        })
      );
    });
  }

  document.getElementById("vagas-count-info").textContent = `Exibindo ${items.length} vagas recentes encontradas`;


  items.forEach(v => {
    const tr = document.createElement("tr");
    const title = cell(tr, "");
    const mobile = element("div", null, "show-mobile");
    const mobileLink = jobLink(v.url, v.titulo, { color: "var(--accent)", fontWeight: "700", textDecoration: "none" });
    if (mobileLink) mobileLink.appendChild(element("span", " ↗", "", { fontSize: "11px", opacity: "0.8" }));
    mobile.appendChild(mobileLink || element("strong", v.titulo));
    mobile.appendChild(element("div", v.empresa, "", { color: "var(--text-muted)", fontSize: "11px", marginTop: "2px" }));
    const desktop = element("div", null, "hide-mobile");
    desktop.appendChild(element("strong", v.titulo));
    title.appendChild(mobile);
    title.appendChild(desktop);
    cell(tr, v.empresa, "hide-mobile");
    cell(tr, element("span", v.area, "badge"), "hide-mobile", { textAlign: "center" });

    // Mostra a cidade quando a localidade traz uma de verdade; o polo
    // regional ("Interior Paulista Ocidental") vira fallback.
    const locNorm = normalizeSearchText(v.localidade || "");
    const cidade = locNorm && !["brasil", "nao informado"].includes(locNorm) ? v.localidade : "";
    const polo = cidade || v.polo || "";
    const modalidade = v.modalidade || "";
    const exibePolo = polo && polo.toLowerCase() !== modalidade.toLowerCase();
    const local = cell(tr, "", "job-location-cell");
    if (exibePolo) local.appendChild(element("span", polo, "job-place"));
    if (modalidade) local.appendChild(element("em", modalidade, "job-mode"));
    if (!local.childNodes.length) local.textContent = "-";
    cell(tr, jobLink(v.url, "↗", { fontSize: "14px", textDecoration: "none" }) || "-", "hide-mobile", { textAlign: "center" });
    tbody.appendChild(tr);
  });
}
