const { ADMIN, GESTOR } = require("./credenciais.js");
const { chromium } = require("playwright-core");

const BASE = process.env.BASE || "http://localhost:3007";
const SHOTS = process.env.SHOTS || ".";
const erros = [];

// Nome único por rodada, para o roteiro reconhecer o que foi ele que criou.
const marca = Date.now().toString().slice(-6);
const LEAD_TESTE = `Cantina E2E ${marca}`;
const ATIVIDADE_TESTE = `Follow-up E2E ${marca}`;
const INTERACAO_TESTE = `Ligação de teste E2E ${marca}`;
const falhasRede = [];

const log = (...a) => console.log(...a);

async function run() {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  page.on("console", (m) => {
    if (m.type() === "error") erros.push(m.text().slice(0, 300));
  });
  page.on("pageerror", (e) => erros.push("PAGEERROR: " + String(e.message).slice(0, 300)));
  page.on("response", (r) => {
    if (r.status() >= 400 && r.url().includes("/api/")) {
      falhasRede.push(`${r.status()} ${r.request().method()} ${r.url().split("/api")[1]}`);
    }
  });

  // ---- login ----
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  await page.fill('[data-testid="login-email-input"]', ADMIN.email);
  await page.fill('[data-testid="login-password-input"]', ADMIN.senha);
  await page.click('[data-testid="login-submit-button"]');
  await page.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  log("OK  login + dashboard carregou");

  const kpi = await page.textContent('[data-testid="kpi-metric-entregas-hoje"]');
  log("    KPI entregas hoje:", kpi.replace(/\s+/g, " ").trim());
  await page.screenshot({ path: `${SHOTS}/01-dashboard.png`, fullPage: true });

  // ---- navegação por todas as telas ----
  const telas = [
    ["sidebar-link-funil", "pipeline-page", "02-funil"],
    ["sidebar-link-atividades", "activities-page", "03-atividades"],
    ["sidebar-link-pedidos", "orders-page", "04-pedidos"],
    ["sidebar-link-restaurantes", "restaurants-page", "05-restaurantes"],
    ["sidebar-link-entregadores", "drivers-page", "06-entregadores"],
    ["sidebar-link-contratos", "contracts-page", "07-contratos"],
    ["sidebar-link-relatorios", "reports-page", "08-relatorios"],
    ["sidebar-link-integracoes", "integrations-page", "09-integracoes"],
    ["sidebar-link-usuarios", "users-page", "10-usuarios"],
  ];
  for (const [link, alvo, shot] of telas) {
    await page.click(`[data-testid="${link}"]`);
    await page.waitForSelector(`[data-testid="${alvo}"]`, { timeout: 15000 });
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${SHOTS}/${shot}.png`, fullPage: true });
    log("OK  tela", alvo);
  }

  // ---- busca global ----
  await page.keyboard.press("Control+K");
  await page.waitForSelector('[data-testid="command-input"]', { timeout: 8000 });
  await page.fill('[data-testid="command-input"]', "burg");
  await page.waitForTimeout(900);
  const nResultados = await page.locator('[data-testid^="search-result-"]').count();
  log("OK  busca global (Ctrl+K):", nResultados, "resultados");
  await page.screenshot({ path: `${SHOTS}/11-busca.png` });
  await page.keyboard.press("Escape");

  // ---- criar lead no funil ----
  await page.click('[data-testid="sidebar-link-funil"]');
  await page.waitForSelector('[data-testid="pipeline-page"]');
  const antes = await page.locator('[data-testid^="lead-card-"]').count();
  await page.click('[data-testid="btn-novo-lead"]');
  await page.fill('[data-testid="lead-name-input"]', LEAD_TESTE);
  await page.click('[data-testid="save-lead-button"]');
  await page.waitForTimeout(1500);
  const depois = await page.locator('[data-testid^="lead-card-"]').count();
  log(`${depois === antes + 1 ? "OK " : "FALHA"} criar lead: ${antes} -> ${depois}`);

  // ---- criar atividade ----
  await page.click('[data-testid="sidebar-link-atividades"]');
  await page.waitForSelector('[data-testid="activities-page"]');
  await page.click('[data-testid="btn-nova-atividade"]');
  await page.fill('[data-testid="activity-title-input"]', ATIVIDADE_TESTE);
  // Prazo explícito para hoje ao meio-dia. O padrão da tela é "daqui a uma
  // hora", e rodando às 23h isso cai no dia seguinte — a tarefa ia para
  // "Próximas" (certo) e esta conferência falhava (errado).
  const hojeMeioDia = (() => {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    const off = d.getTimezoneOffset() * 60000;
    return new Date(d.getTime() - off).toISOString().slice(0, 16);
  })();
  await page.fill('[data-testid="activity-due-input"]', hojeMeioDia);
  await page.click('[data-testid="save-activity-button"]');
  await page.waitForTimeout(1500);
  const temAtividade = await page.locator(`text=${ATIVIDADE_TESTE}`).count();
  log(`${temAtividade > 0 ? "OK " : "FALHA"} criar atividade (aparece na aba Hoje: ${temAtividade})`);

  // ---- confirmação antes de excluir ----
  await page.click('[data-testid="sidebar-link-restaurantes"]');
  await page.waitForSelector('[data-testid="restaurants-page"]');
  const temBotaoExcluir = await page.locator('[data-testid="delete-restaurante-0"]').count();
  if (temBotaoExcluir) {
    await page.click('[data-testid="delete-restaurante-0"]');
    await page.waitForSelector('[data-testid="confirm-dialog"]', { timeout: 6000 });
    log("OK  exclusão pede confirmação");
    await page.screenshot({ path: `${SHOTS}/12-confirmacao.png` });
    await page.click('[data-testid="confirm-cancel"]');
    await page.waitForTimeout(500);
  }

  // ---- detalhe com timeline ----
  await page.click('[data-testid="open-restaurante-detail-0"]');
  await page.waitForSelector('[data-testid="detail-sheet"]', { timeout: 8000 });
  await page.fill('[data-testid="detail-interaction-input"]', INTERACAO_TESTE);
  await page.click('[data-testid="detail-interaction-save"]');
  await page.waitForTimeout(1500);
  const naTimeline = await page.locator(`text=${INTERACAO_TESTE}`).count();
  log(`${naTimeline > 0 ? "OK " : "FALHA"} interação entra na linha do tempo`);
  await page.screenshot({ path: `${SHOTS}/13-detalhe.png` });
  await page.keyboard.press("Escape");

  // ---- responsivo ----
  await page.setViewportSize({ width: 390, height: 844 });
  await page.click('[data-testid="sidebar-link-dashboard"]').catch(() => {});
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="dashboard-page"]');
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${SHOTS}/14-mobile.png`, fullPage: true });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  log(`${overflow <= 1 ? "OK " : "FALHA"} sem rolagem horizontal no celular (excesso: ${overflow}px)`);

  // ---- perfil gestor: ações de admin escondidas ----
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.click('[data-testid="open-account-menu"]');
  await page.click('[data-testid="logout-button"]');
  await page.waitForSelector('[data-testid="login-form"]', { timeout: 10000 });
  await page.fill('[data-testid="login-email-input"]', GESTOR.email);
  await page.fill('[data-testid="login-password-input"]', GESTOR.senha);
  await page.click('[data-testid="login-submit-button"]');
  await page.waitForSelector('[data-testid="dashboard-page"]', { timeout: 15000 });
  const linkUsuarios = await page.locator('[data-testid="sidebar-link-usuarios"]').count();
  await page.goto(`${BASE}/restaurantes`, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="restaurants-page"]');
  const lixeiraGestor = await page.locator('[data-testid="delete-restaurante-0"]').count();
  log(`${linkUsuarios === 0 ? "OK " : "FALHA"} gestor não vê menu Usuários`);
  log(`${lixeiraGestor === 0 ? "OK " : "FALHA"} gestor não vê botão de excluir`);
  await page.screenshot({ path: `${SHOTS}/15-gestor.png`, fullPage: true });

  // Limpeza: o lead existe só por causa deste roteiro. Volta para o
  // administrador — excluir é ação de admin, e é justamente o que o bloco
  // acima acabou de confirmar que o gestor não enxerga.
  await page.click('[data-testid="open-account-menu"]');
  await page.click('[data-testid="logout-button"]');
  await page.waitForSelector('[data-testid="login-form"]', { timeout: 10000 });
  await page.fill('[data-testid="login-email-input"]', ADMIN.email);
  await page.fill('[data-testid="login-password-input"]', ADMIN.senha);
  await page.click('[data-testid="login-submit-button"]');
  await page.waitForSelector('[data-testid="dashboard-page"]', { timeout: 15000 });

  await page.goto(`${BASE}/funil`, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="pipeline-page"]', { timeout: 20000 });
  const cartao = page.locator(`[data-testid^="lead-card-"]:has-text("${LEAD_TESTE}")`).first();
  if (await cartao.count()) {
    // O botão de excluir mora dentro do próprio cartão.
    const excluir = cartao.locator('[data-testid^="delete-lead-"]').first();
    if (await excluir.count()) {
      await excluir.click();
      await page.click('[data-testid="confirm-accept"]');
      await page.waitForTimeout(1500);
    }
  }
  const semLead = (await page.locator(`text=${LEAD_TESTE}`).count()) === 0;
  log(`${semLead ? "OK " : "AVISO"} lead de teste removido`);

  // A atividade também: sem isso, cada rodada deixava mais um "Follow-up"
  // vencendo na agenda de quem usa o sistema de verdade.
  await page.goto(`${BASE}/atividades`, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="activities-page"]', { timeout: 20000 });
  // "Todas": a interação registrada na linha do tempo nasce concluída e não
  // aparece na aba "Hoje" — procurar só ali dava uma limpeza que não limpava.
  await page.click('[data-testid="activity-tab-todas"]');
  await page.waitForTimeout(1200);
  const linha = page.locator(`[data-testid^="activity-row-"]:has-text("${ATIVIDADE_TESTE}")`).first();
  if (await linha.count()) {
    const apagar = linha.locator('[data-testid^="delete-activity-"]').first();
    if (await apagar.count()) {
      await apagar.click();
      await page.click('[data-testid="confirm-accept"]');
      await page.waitForTimeout(1500);
    }
  }
  const semAtividade = (await page.locator(`text=${ATIVIDADE_TESTE}`).count()) === 0;
  log(`${semAtividade ? "OK " : "AVISO"} atividade de teste removida`);

  // A interação registrada na linha do tempo também é uma atividade, e
  // engordava o histórico de um restaurante real a cada rodada.
  const linhaInteracao = page
    .locator(`[data-testid^="activity-row-"]:has-text("${INTERACAO_TESTE}")`)
    .first();
  if (await linhaInteracao.count()) {
    const apagarInteracao = linhaInteracao.locator('[data-testid^="delete-activity-"]').first();
    if (await apagarInteracao.count()) {
      await apagarInteracao.click();
      await page.click('[data-testid="confirm-accept"]');
      await page.waitForTimeout(1500);
    }
  }
  const semInteracao = (await page.locator(`text=${INTERACAO_TESTE}`).count()) === 0;
  log(`${semInteracao ? "OK " : "AVISO"} interação de teste removida`);

  await browser.close();

  log("\n--- erros de console ---");
  log(erros.length ? [...new Set(erros)].join("\n") : "nenhum");
  log("--- respostas de API com erro ---");
  log(falhasRede.length ? [...new Set(falhasRede)].join("\n") : "nenhuma");
}

run().catch((e) => {
  console.error("FALHA NO ROTEIRO:", e.message);
  console.error("erros de console:", [...new Set(erros)].slice(0, 10).join("\n"));
  process.exit(1);
});
