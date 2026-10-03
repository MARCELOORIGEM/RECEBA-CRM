const { ADMIN } = require("./credenciais.js");
const { chromium } = require("playwright-core");
const BASE = process.env.BASE || "http://localhost:3007";
const erros = [];

// Nome e CNPJ únicos por rodada: com valores fixos, o cadastro de uma rodada
// sobrevivia e fazia a seguinte (e o teste de CNPJ duplicado do pytest) bater
// em 409.
const marca = Date.now().toString().slice(-6);
const RESTAURANTE = `Trattoria E2E ${marca}`;
const FORMULARIO = `Parceiro E2E ${marca}`;
const CNPJ = `11.222.${marca}/0001-44`;

// LIMPA_BALDE: o limite de envios por IP é por dispositivo, e todo roteiro
// roda do mesmo 127.0.0.1 — sem zerar, a segunda rodada bate em 429.
const { execFileSync } = require("child_process");
const limparBaldeDeEnvios = () => {};

(async () => {
  limparBaldeDeEnvios();
  const b = await chromium.launch({ channel: "chrome", headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  p.on("pageerror", (e) => erros.push("PAGEERROR: " + e.message.slice(0, 200)));
  p.on("console", (m) => { if (m.type() === "error") erros.push(m.text().slice(0, 200)); });

  await p.goto(BASE, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  await p.waitForTimeout(1500);
  await p.screenshot({ path: "./shots/40-login-miliano.png" });
  console.log("OK  login renderizou |", await p.title());

  await p.fill('[data-testid="login-email-input"]', ADMIN.email);
  await p.fill('[data-testid="login-password-input"]', ADMIN.senha);
  await p.click('[data-testid="login-submit-button"]');
  await p.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  await p.waitForTimeout(1200);
  await p.screenshot({ path: "./shots/41-dashboard-miliano.png" });
  console.log("OK  dashboard |", await p.title());

  // --- construir um formulário ---
  await p.click('[data-testid="sidebar-link-formularios"]');
  await p.waitForSelector('[data-testid="forms-page"]', { timeout: 15000 });
  await p.click('[data-testid="btn-novo-formulario"]');
  await p.waitForSelector('[data-testid="form-title-input"]', { timeout: 8000 });
  // O formulário novo já nasce com o modelo padrão: basta escolher o destino
  // e ajustar o título.
  await p.click('[data-testid="form-target"]');
  await p.waitForTimeout(400);
  await p.getByRole("option", { name: "Restaurante" }).click();
  await p.waitForTimeout(500);
  await p.fill('[data-testid="form-title-input"]', FORMULARIO);
  await p.waitForTimeout(300);
  await p.screenshot({ path: "./shots/42-construtor.png" });
  await p.click('[data-testid="save-form-button"]');
  await p.waitForTimeout(1800);
  const cards = await p.locator('[data-testid^="form-card-"]').count();
  console.log(`${cards > 0 ? "OK " : "FALHA"} formulário criado (${cards} card)`);
  await p.screenshot({ path: "./shots/43-formularios.png", fullPage: true });

  const slugTexto = await p.locator('[data-testid="form-card-0"] code').first().innerText();
  const slug = slugTexto.replace("/f/", "").trim();
  console.log("    slug:", slug);

  // --- página pública, em aba anônima (sem cookie de sessão) ---
  const ctx2 = await b.newContext({ viewport: { width: 430, height: 900 } });
  const pub = await ctx2.newPage();
  pub.on("pageerror", (e) => erros.push("PUBLIC PAGEERROR: " + e.message.slice(0, 200)));
  await pub.goto(`${BASE}/f/${slug}`, { waitUntil: "networkidle" });
  await pub.waitForSelector('[data-testid="public-form"]', { timeout: 15000 });
  await pub.waitForTimeout(900);
  await pub.screenshot({ path: "./shots/44-form-publico-mobile.png", fullPage: true });
  console.log("OK  formulário público abre sem sessão |", await pub.title());

  const overflow = await pub.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  console.log(`${overflow <= 1 ? "OK " : "FALHA"} sem rolagem horizontal no celular (${overflow}px)`);

  await pub.fill('[data-testid="public-field-name"]', RESTAURANTE);
  await pub.fill('[data-testid="public-field-cnpj"]', CNPJ);
  await pub.click('[data-testid="public-field-category"]');
  await pub.waitForTimeout(400);
  await pub.getByRole("option", { name: "Pizzaria" }).click();
  await pub.fill('[data-testid="public-field-contact_person"]', "Sra. Bianca");
  await pub.fill('[data-testid="public-field-phone"]', "(11) 97777-0000");
  await pub.fill('[data-testid="public-field-address"]', "Rua Teste, 100 - Centro");
  // O aviso de privacidade trava o envio até alguém marcar — a API
  // exige o mesmo.
  await pub.check('[data-testid="public-form-aceite"]');
  await pub.click('[data-testid="public-form-submit"]');
  await pub.waitForSelector('[data-testid="public-form-success"]', { timeout: 15000 });
  await pub.screenshot({ path: "./shots/45-form-sucesso.png" });
  console.log("OK  envio público concluído");

  // --- o cadastro chegou no CRM? ---
  await p.goto(`${BASE}/restaurantes`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="restaurants-page"]');
  await p.fill('[data-testid="search-restaurante-input"]', RESTAURANTE);
  await p.waitForTimeout(1500);
  const achou = await p.locator(`text=${RESTAURANTE}`).count();
  const emAnalise = await p.locator("text=Em análise").count();
  console.log(`${achou > 0 ? "OK " : "FALHA"} cadastro entrou em Restaurantes`);
  console.log(`${emAnalise > 0 ? "OK " : "FALHA"} chegou com status "Em análise"`);
  await p.screenshot({ path: "./shots/46-cadastro-recebido.png" });

  // Limpeza: o cadastro e o formulário existem só por causa deste roteiro, e
  // ficariam misturados ao dado real do CRM.
  const apagar = await p.$('[data-testid="delete-restaurante-0"]');
  if (apagar) {
    await apagar.click();
    await p.click('[data-testid="confirm-accept"]');
    await p.waitForTimeout(1200);
  }
  const limpo = (await p.locator(`text=${RESTAURANTE}`).count()) === 0;
  console.log(`${limpo ? "OK " : "AVISO"} cadastro de teste removido`);

  // E o formulário, que também era criado toda rodada.
  await p.goto(`${BASE}/formularios`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="forms-page"]', { timeout: 20000 });
  const cartao = p.locator(`[data-testid^="form-card-"]:has-text("${FORMULARIO}")`).first();
  if (await cartao.count()) {
    const apagarForm = await cartao.locator('[data-testid^="delete-form-"]').first();
    if (await apagarForm.count()) {
      await apagarForm.click();
      await p.click('[data-testid="confirm-accept"]');
      // O formulário recebeu uma resposta no roteiro: a tela pede uma segunda
      // confirmação antes de apagar o histórico junto.
      await p.waitForTimeout(1200);
      const segunda = await p.$('[data-testid="confirm-accept"]');
      if (segunda) {
        await segunda.click();
        await p.waitForTimeout(1500);
      }
    }
  }
  const semForm = (await p.locator(`text=${FORMULARIO}`).count()) === 0;
  console.log(`${semForm ? "OK " : "AVISO"} formulário de teste removido`);

  await b.close();
  console.log("\n--- erros ---");
  console.log(erros.length ? [...new Set(erros)].join("\n") : "nenhum");
})().catch((e) => {
  console.error("FALHA:", e.message);
  console.error([...new Set(erros)].slice(0, 8).join("\n"));
  process.exit(1);
});
