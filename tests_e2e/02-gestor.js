const { GESTOR } = require("./credenciais.js");
const { chromium } = require("playwright-core");
const BASE = process.env.BASE || "http://localhost:3007";
const erros = [];

(async () => {
  const b = await chromium.launch({ channel: "chrome", headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  p.on("pageerror", (e) => erros.push("PAGEERROR: " + e.message.slice(0, 160)));
  p.on("console", (m) => { if (m.type() === "error") erros.push(m.text().slice(0, 160)); });

  await p.goto(BASE, { waitUntil: "networkidle" });
  await p.fill('[data-testid="login-email-input"]', GESTOR.email);
  await p.fill('[data-testid="login-password-input"]', GESTOR.senha);
  await p.click('[data-testid="login-submit-button"]');
  await p.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  console.log("OK  login como GESTOR");

  // --- minha conta: troca de senha (o gestor nao tinha como) ---
  await p.click('[data-testid="open-account-menu"]');
  await p.click('[data-testid="open-account"]');
  await p.waitForSelector('[data-testid="senha-atual-input"]', { timeout: 8000 });
  await p.fill('[data-testid="senha-atual-input"]', GESTOR.senha);
  await p.fill('[data-testid="senha-nova-input"]', "SenhaNova@2026");
  await p.fill('[data-testid="senha-confirma-input"]', "SenhaNova@2026");
  await p.click('[data-testid="salvar-senha-button"]');
  await p.waitForTimeout(1500);
  console.log("OK  gestor trocou a propria senha");
  await p.screenshot({ path: "./shots/20-conta.png" });

  // confere: relogar com a nova e desfazer
  await p.click('[data-testid="open-account-menu"]');
  await p.click('[data-testid="logout-button"]');
  await p.waitForSelector('[data-testid="login-form"]');
  await p.fill('[data-testid="login-email-input"]', GESTOR.email);
  await p.fill('[data-testid="login-password-input"]', "SenhaNova@2026");
  await p.click('[data-testid="login-submit-button"]');
  await p.waitForSelector('[data-testid="dashboard-page"]', { timeout: 15000 });
  console.log("OK  login com a senha nova funciona");
  await p.click('[data-testid="open-account-menu"]');
  await p.click('[data-testid="open-account"]');
  await p.waitForSelector('[data-testid="senha-atual-input"]');
  await p.fill('[data-testid="senha-atual-input"]', "SenhaNova@2026");
  await p.fill('[data-testid="senha-nova-input"]', GESTOR.senha);
  await p.fill('[data-testid="senha-confirma-input"]', GESTOR.senha);
  await p.click('[data-testid="salvar-senha-button"]');
  await p.waitForTimeout(1500);
  console.log("OK  senha original restaurada");

  // --- editar pedido ---
  await p.goto(`${BASE}/pedidos`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="orders-page"]');
  await p.click('[data-testid="edit-order-0"]');
  await p.waitForSelector('[data-testid="order-customer-input"]', { timeout: 8000 });
  const antes = await p.inputValue('[data-testid="order-customer-input"]');
  await p.fill('[data-testid="order-customer-input"]', antes + " (editado)");
  await p.click('[data-testid="save-order-button"]');
  await p.waitForTimeout(1800);
  const editado = await p.locator(`text=${antes} (editado)`).count();
  console.log(`${editado > 0 ? "OK " : "FALHA"} editar pedido (cliente "${antes}" -> editado)`);
  await p.screenshot({ path: "./shots/21-pedido-editado.png" });
  // desfaz
  await p.click('[data-testid="edit-order-0"]');
  await p.waitForSelector('[data-testid="order-customer-input"]');
  await p.fill('[data-testid="order-customer-input"]', antes);
  await p.click('[data-testid="save-order-button"]');
  await p.waitForTimeout(1200);

  // --- mover lead pelo menu (sem arrastar) ---
  await p.goto(`${BASE}/funil`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="pipeline-page"]');
  const card = p.locator('[data-testid^="lead-card-"]').first();
  const leadId = (await card.getAttribute("data-testid")).replace("lead-card-", "");
  await card.hover();
  await p.click(`[data-testid="move-lead-${leadId}"]`);
  // O menu não oferece a etapa em que o lead já está, e o primeiro cartão da
  // tela muda conforme a base. Pegar a primeira opção disponível, em vez de
  // uma etapa fixa, deixa o roteiro independente do estado do funil.
  await p.waitForSelector('[data-testid^="move-to-"]', { timeout: 8000 });
  await p.screenshot({ path: "./shots/22-mover-lead.png" });
  const opcao = p.locator('[data-testid^="move-to-"]').first();
  const destino = (await opcao.getAttribute("data-testid")).replace("move-to-", "");
  await opcao.click();
  await p.waitForTimeout(1500);
  const naColuna = await p.locator(`[data-testid="pipeline-col-${destino}"]`)
    .locator(`[data-testid="lead-card-${leadId}"]`).count();
  console.log(`${naColuna > 0 ? "OK " : "FALHA"} mover lead pelo menu (sem arrastar)`);

  // navegacao por teclado ate o menu
  await p.keyboard.press("Tab");
  const focoOk = await p.evaluate(() => document.activeElement?.tagName);
  console.log(`OK  foco por teclado alcanca elementos interativos (${focoOk})`);

  // --- relatorios ---
  await p.goto(`${BASE}/relatorios`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="reports-page"]');
  await p.waitForTimeout(1200);
  await p.screenshot({ path: "./shots/23-relatorios.png", fullPage: true });
  console.log("OK  relatorios carrega");

  await b.close();
  console.log("\n--- erros ---");
  console.log(erros.length ? [...new Set(erros)].join("\n") : "nenhum");
})().catch((e) => {
  console.error("FALHA:", e.message);
  console.error([...new Set(erros)].slice(0, 6).join("\n"));
  process.exit(1);
});
