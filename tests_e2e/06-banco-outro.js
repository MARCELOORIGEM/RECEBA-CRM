const { ADMIN } = require("./credenciais.js");
const { chromium } = require("playwright-core");
const { execFileSync } = require("child_process");
const BASE = process.env.BASE || "http://localhost:3007";
const erros = [];

// Nome único por rodada: com um nome fixo, o cadastro de uma rodada
// sobrevivia e atrapalhava a seguinte.
const marca06 = Date.now().toString().slice(-6);
const NOME_TESTE = `Entregador Outro ${marca06}`;
const limpar = () =>
  execFileSync("C:/Users/DELL/receba-crm/.venv/Scripts/python.exe", [
    "-c",
    "from pymongo import MongoClient;d=MongoClient('mongodb://localhost:27017')['test_database'];"
    + "d.form_submissions.delete_many({'ip':'127.0.0.1'});d.login_attempts.delete_many({})",
  ]);

(async () => {
  limpar();
  const b = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await b.newContext({ viewport: { width: 430, height: 940 } });
  const pub = await ctx.newPage();
  pub.on("pageerror", (e) => erros.push(e.message.slice(0, 140)));

  await pub.goto(`${BASE}/f/cadastro-de-entregadores`, { waitUntil: "networkidle" });
  await pub.waitForSelector('[data-testid="public-form"]', { timeout: 20000 });
  await pub.waitForTimeout(700);

  // Banco agora é múltipla escolha, não lista suspensa
  const radiosBanco = await pub.locator('[data-testid^="public-option-bank-"]').count();
  console.log(`${radiosBanco >= 15 ? "OK " : "FALHA"} Banco é múltipla escolha (${radiosBanco} opções, com "Outro:")`);

  await pub.fill('[data-testid="public-field-name"]', NOME_TESTE);
  await pub.fill('[data-testid="public-field-cpf"]', "529.982.247-25");
  await pub.fill('[data-testid="public-field-phone"]', "(81) 98888-7777");
  await pub.click('[data-testid="public-option-vehicle_type-Bicicleta"]');

  // "Outro:" abre campo de escrita
  await pub.click('[data-testid="public-option-bank-outro"]');
  await pub.waitForSelector('[data-testid="public-other-bank"]', { timeout: 6000 });
  console.log("OK  'Outro:' abre campo de escrita livre");
  await pub.fill('[data-testid="public-other-bank"]', "Banco Cooperativo do Nordeste");

  await pub.fill('[data-testid="public-field-bank_agency"]', "Não se aplica");
  await pub.click('[data-testid="public-option-account_type-Conta Corrente"]');
  await pub.fill('[data-testid="public-field-bank_account"]', "98765432-1");
  await pub.click('[data-testid="public-option-pix_key_type-Chave aleatória"]');
  await pub.fill('[data-testid="public-field-pix_key"]', "abc-123-def-456");
  await pub.screenshot({ path: "./shots/90-form-outro.png", fullPage: true });

  // O aviso de privacidade trava o envio até alguém marcar — a API
  // exige o mesmo.
  await pub.check('[data-testid="public-form-aceite"]');
  await pub.click('[data-testid="public-form-submit"]');
  await pub.waitForSelector('[data-testid="public-form-success"]', { timeout: 15000 });
  console.log("OK  envio com banco fora da lista");

  // --- o dado chegou ao cadastro? ---
  const p = await b.newPage({ viewport: { width: 1440, height: 980 } });
  p.on("pageerror", (e) => erros.push(e.message.slice(0, 140)));
  await p.goto(BASE, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  await p.fill('[data-testid="login-email-input"]', ADMIN.email);
  await p.fill('[data-testid="login-password-input"]', ADMIN.senha);
  await p.click('[data-testid="login-submit-button"]');
  await p.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });

  await p.goto(`${BASE}/entregadores`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="drivers-page"]');
  await p.fill('[data-testid="search-entregador-input"]', NOME_TESTE);
  await p.waitForTimeout(1600);
  await p.click('[data-testid="open-driver-detail-0"]');
  await p.waitForSelector('[data-testid="detail-sheet"]', { timeout: 8000 });
  await p.waitForTimeout(600);
  const banco = await p.locator("text=Banco Cooperativo do Nordeste").count();
  const pix = await p.locator("text=abc-123-def-456").count();
  console.log(`${banco ? "OK " : "FALHA"} banco escrito à mão chegou no cadastro`);
  console.log(`${pix ? "OK " : "FALHA"} chave PIX chegou no cadastro`);
  await p.screenshot({ path: "./shots/91-cadastro-pagamento.png" });
  await p.keyboard.press("Escape");
  await p.waitForTimeout(400);

  // --- editar os dados de pagamento pelo cadastro ---
  await p.click('[data-testid="edit-driver-0"]');
  await p.waitForSelector('[data-testid="driver-pix-input"]', { timeout: 8000 });
  const cpfNoForm = await p.inputValue('[data-testid="driver-cpf-input"]');
  console.log(`${cpfNoForm === "52998224725" ? "OK " : "FALHA"} edição traz o CPF preenchido (${cpfNoForm})`);
  await p.fill('[data-testid="driver-pix-input"]', "chave-corrigida-999");
  await p.fill('[data-testid="driver-account-input"]', "11112222-3");
  await p.screenshot({ path: "./shots/92-editar-pagamento.png" });
  await p.click('[data-testid="save-driver-button"]');
  await p.waitForTimeout(1800);
  await p.click('[data-testid="open-driver-detail-0"]');
  await p.waitForSelector('[data-testid="detail-sheet"]', { timeout: 8000 });
  await p.waitForTimeout(500);
  const corrigido = await p.locator("text=chave-corrigida-999").count();
  console.log(`${corrigido ? "OK " : "FALHA"} equipe consegue corrigir os dados de pagamento`);


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
  console.error([...new Set(erros)].slice(0, 5).join("\n"));
  process.exit(1);
});
