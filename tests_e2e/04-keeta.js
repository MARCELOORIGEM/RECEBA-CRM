const { ADMIN } = require("./credenciais.js");
const { chromium } = require("playwright-core");
const BASE = process.env.BASE || "http://localhost:3007";
const erros = [];

// Nome único por rodada: com um nome fixo, o cadastro de uma rodada
// sobrevivia e atrapalhava a seguinte.
const marca04 = Date.now().toString().slice(-6);
const NOME_TESTE = `Entregador Keeta ${marca04}`;

// LIMPA_BALDE: o limite de envios por IP é por dispositivo, e todo roteiro
// roda do mesmo 127.0.0.1 — sem zerar, a segunda rodada bate em 429.
const { execFileSync } = require("child_process");
const limparBaldeDeEnvios = () => {};

(async () => {
  limparBaldeDeEnvios();
  const b = await chromium.launch({ channel: "chrome", headless: true });

  // --- formulário público, sem sessão, em celular ---
  const ctx = await b.newContext({ viewport: { width: 430, height: 940 } });
  const pub = await ctx.newPage();
  pub.on("pageerror", (e) => erros.push("PUB: " + e.message.slice(0, 140)));
  await pub.goto(`${BASE}/f/cadastro-de-entregadores`, { waitUntil: "networkidle" });
  await pub.waitForSelector('[data-testid="public-form"]', { timeout: 20000 });
  await pub.waitForTimeout(900);
  await pub.screenshot({ path: "./shots/70-form-keeta.png", fullPage: true });
  console.log("OK  formulário público abre |", await pub.title());

  await pub.fill('[data-testid="public-field-name"]', NOME_TESTE);
  await pub.fill('[data-testid="public-field-cpf"]', "529.982.247-25");
  const cpf = await pub.inputValue('[data-testid="public-field-cpf"]');
  console.log(`${cpf === "52998224725" ? "OK " : "FALHA"} CPF aceita só dígitos ("529.982.247-25" -> "${cpf}")`);

  await pub.fill('[data-testid="public-field-phone"]', "(81) 98888-1234");
  await pub.click('[data-testid="public-option-vehicle_type-Moto"]');
  // Banco é múltipla escolha (botões), como no formulário original.
  await pub.click('[data-testid="public-option-bank-Nubank"]');
  await pub.fill('[data-testid="public-field-bank_agency"]', "0001");
  await pub.click('[data-testid="public-option-account_type-Conta Corrente"]');
  await pub.fill('[data-testid="public-field-bank_account"]', "12345678-9");
  await pub.click('[data-testid="public-option-pix_key_type-CPF"]');
  await pub.fill('[data-testid="public-field-pix_key"]', "52998224725");
  await pub.waitForTimeout(300);
  await pub.screenshot({ path: "./shots/71-form-preenchido.png", fullPage: true });

  // O aviso de privacidade trava o envio até alguém marcar — a API
  // exige o mesmo.
  await pub.check('[data-testid="public-form-aceite"]');
  await pub.click('[data-testid="public-form-submit"]');
  await pub.waitForSelector('[data-testid="public-form-success"]', { timeout: 15000 });
  await pub.screenshot({ path: "./shots/72-form-sucesso.png" });
  console.log("OK  envio concluído");

  const overflow = await pub.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  console.log(`${overflow <= 1 ? "OK " : "FALHA"} sem rolagem horizontal (${overflow}px)`);

  // --- CRM: menu no topo + parceria + dados bancários ---
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  p.on("pageerror", (e) => erros.push("CRM: " + e.message.slice(0, 140)));
  await p.goto(BASE, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  await p.fill('[data-testid="login-email-input"]', ADMIN.email);
  await p.fill('[data-testid="login-password-input"]', ADMIN.senha);
  await p.click('[data-testid="login-submit-button"]');
  await p.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  await p.waitForTimeout(1200);
  await p.screenshot({ path: "./shots/73-crm-topo.png" });
  console.log("OK  dashboard com menu no topo");

  const nav = await p.locator('nav[aria-label="Navegação principal"]').first().boundingBox();
  const main = await p.locator("main").boundingBox();
  console.log(`${nav.y < 200 ? "OK " : "FALHA"} menu está no topo (y=${Math.round(nav.y)})`);
  console.log(`${main.width > 1300 ? "OK " : "FALHA"} conteúdo usa a largura toda (${Math.round(main.width)}px)`);
  console.log(`${await p.locator('[data-testid="faixa-keeta"]').count() ? "OK " : "FALHA"} faixa da parceria no dashboard`);
  console.log(`${await p.locator('[data-testid="selo-keeta"]').count() ? "OK " : "FALHA"} selo da parceria na barra do topo`);

  // menu da conta
  await p.click('[data-testid="open-account-menu"]');
  await p.waitForSelector('[data-testid="logout-button"]', { timeout: 6000 });
  console.log("OK  menu da conta abre com Sair");
  await p.keyboard.press("Escape");

  // dados bancários no detalhe do entregador
  await p.goto(`${BASE}/entregadores`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="drivers-page"]');
  await p.fill('[data-testid="search-entregador-input"]', NOME_TESTE);
  await p.waitForTimeout(1500);
  await p.click('[data-testid="open-driver-detail-0"]');
  await p.waitForSelector('[data-testid="detail-sheet"]', { timeout: 8000 });
  await p.waitForTimeout(600);
  const temPix = await p.locator("text=52998224725").count();
  const temBanco = await p.locator("text=Nubank").count();
  console.log(`${temPix && temBanco ? "OK " : "FALHA"} dados bancários e PIX no cadastro do entregador`);
  await p.screenshot({ path: "./shots/74-entregador-pagamento.png" });

  // mobile do CRM
  const ctx3 = await b.newContext({ viewport: { width: 390, height: 844 } });
  const p3 = await ctx3.newPage();
  await p3.goto(BASE, { waitUntil: "networkidle" });
  await p3.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  await p3.fill('[data-testid="login-email-input"]', ADMIN.email);
  await p3.fill('[data-testid="login-password-input"]', ADMIN.senha);
  await p3.click('[data-testid="login-submit-button"]');
  await p3.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  await p3.click('[data-testid="open-sidebar"]');
  await p3.waitForTimeout(600);
  await p3.screenshot({ path: "./shots/75-crm-mobile-menu.png" });
  console.log(`${await p3.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth) <= 1 ? "OK " : "FALHA"} CRM sem rolagem horizontal no celular`);


  // Limpeza: o entregador existe só por causa deste roteiro e ficaria
  // misturado ao cadastro real da operação.
  await p.goto(`${BASE}/entregadores`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="drivers-page"]', { timeout: 20000 });
  await p.fill('[data-testid="search-entregador-input"]', NOME_TESTE);
  await p.waitForTimeout(1500);
  const apagar = await p.$('[data-testid="delete-driver-0"]');
  if (apagar) {
    await apagar.click();
    await p.click('[data-testid="confirm-accept"]');
    await p.waitForTimeout(1200);
  }
  const limpo = (await p.locator(`text=${NOME_TESTE}`).count()) === 0;
  console.log(`${limpo ? "OK " : "AVISO"} entregador de teste removido`);


  // E a resposta que ficou no formulário, com CPF e conta dentro. Vai pelo
  // botão da tela, que é o mesmo caminho de um pedido de exclusão de dados.
  await p.goto(`${BASE}/formularios`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="forms-page"]', { timeout: 20000 });
  const cartaoForm = p
    .locator('[data-testid^="form-card-"]:has-text("Cadastro de Entregadores")')
    .first();
  if (await cartaoForm.count()) {
    await cartaoForm.locator('[data-testid^="view-submissions-"]').first().click();
    await p.waitForTimeout(1500);
    const linhaResposta = p
      .locator(`[data-testid^="submission-row-"]:has-text("${NOME_TESTE}")`)
      .first();
    if (await linhaResposta.count()) {
      await linhaResposta.locator('[data-testid^="delete-submission-"]').first().click();
      await p.click('[data-testid="confirm-accept"]');
      await p.waitForTimeout(1500);
    }
    const semResposta =
      (await p.locator(`[data-testid^="submission-row-"]:has-text("${NOME_TESTE}")`).count()) === 0;
    console.log(`${semResposta ? "OK " : "AVISO"} resposta de teste removida`);
    await p.keyboard.press("Escape");
  }

  await b.close();
  console.log("\nerros:", erros.length ? [...new Set(erros)].join(" | ") : "nenhum");
})().catch((e) => {
  console.error("FALHA:", e.message);
  console.error([...new Set(erros)].slice(0, 6).join("\n"));
  process.exit(1);
});
