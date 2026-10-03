const { ADMIN } = require("./credenciais.js");
const { chromium } = require("playwright-core");
const BASE = process.env.BASE || "http://localhost:3007";
const erros = [];

(async () => {
  const b = await chromium.launch({ channel: "chrome", headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 980 } });
  p.on("pageerror", (e) => erros.push(e.message.slice(0, 140)));
  await p.goto(BASE, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  await p.fill('[data-testid="login-email-input"]', ADMIN.email);
  await p.fill('[data-testid="login-password-input"]', ADMIN.senha);
  await p.click('[data-testid="login-submit-button"]');
  await p.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });

  await p.click('[data-testid="sidebar-link-formularios"]');
  await p.waitForSelector('[data-testid="forms-page"]', { timeout: 15000 });
  await p.click('[data-testid="btn-novo-formulario"]');
  await p.waitForSelector('[data-testid="form-title-input"]', { timeout: 8000 });
  await p.waitForTimeout(600);

  const titulo = await p.inputValue('[data-testid="form-title-input"]');
  const campos = await p.locator('[data-testid^="form-field-"]').count();
  console.log(`${campos === 10 ? "OK " : "FALHA"} novo formulário já vem com o modelo (${campos} perguntas, "${titulo}")`);

  const rotulos = [];
  for (let i = 0; i < campos; i++) rotulos.push(await p.inputValue(`[data-testid="field-label-${i}"]`));
  console.log("    perguntas:", rotulos.join(" | "));
  await p.screenshot({ path: "./shots/80-modelo-padrao.png" });

  // --- EDITAR ---
  await p.fill('[data-testid="field-label-0"]', "Nome completo do entregador");
  console.log("OK  editar pergunta");

  // --- EXCLUIR ---
  await p.click('[data-testid="remove-field-9"]');
  await p.waitForTimeout(300);
  const aposRemover = await p.locator('[data-testid^="form-field-"]').count();
  console.log(`${aposRemover === campos - 1 ? "OK " : "FALHA"} excluir pergunta (${campos} -> ${aposRemover})`);

  // A pergunta removida volta a ficar disponível para repor
  const podeRepor = await p.locator('[data-testid="add-preset-pix_key"]').count();
  console.log(`${podeRepor ? "OK " : "FALHA"} pergunta removida fica à mão para repor`);

  // --- ADICIONAR ---
  await p.click('[data-testid="add-field"]');
  await p.waitForTimeout(300);
  const idx = (await p.locator('[data-testid^="form-field-"]').count()) - 1;
  await p.fill(`[data-testid="field-label-${idx}"]`, "Tem baú térmico?");
  const aposAdd = await p.locator('[data-testid^="form-field-"]').count();
  console.log(`${aposAdd === aposRemover + 1 ? "OK " : "FALHA"} adicionar pergunta nova (${aposRemover} -> ${aposAdd})`);

  // --- REPOR O MODELO ---
  await p.click('[data-testid="apply-template"]');
  await p.waitForSelector('[data-testid="confirm-dialog"]', { timeout: 6000 });
  await p.click('[data-testid="confirm-accept"]');
  await p.waitForTimeout(500);
  const reposto = await p.locator('[data-testid^="form-field-"]').count();
  const label0 = await p.inputValue('[data-testid="field-label-0"]');
  console.log(`${reposto === 10 && label0 === "Nome completo" ? "OK " : "FALHA"} repor modelo padrão (${reposto} perguntas, 1ª = "${label0}")`);

  // --- TROCAR DESTINO TROCA O MODELO ---
  await p.click('[data-testid="form-target"]');
  await p.waitForTimeout(300);
  await p.getByRole("option", { name: "Restaurante" }).click();
  await p.waitForTimeout(500);
  const camposRest = await p.locator('[data-testid^="form-field-"]').count();
  const tituloRest = await p.inputValue('[data-testid="form-title-input"]');
  console.log(`${camposRest === 8 ? "OK " : "FALHA"} trocar destino troca o modelo (${camposRest} perguntas, "${tituloRest}")`);
  await p.screenshot({ path: "./shots/81-modelo-restaurante.png" });

  await b.close();
  console.log("\nerros:", erros.length ? [...new Set(erros)].join(" | ") : "nenhum");
})().catch((e) => {
  console.error("FALHA:", e.message);
  console.error([...new Set(erros)].slice(0, 5).join("\n"));
  process.exit(1);
});
