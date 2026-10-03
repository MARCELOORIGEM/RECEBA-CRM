// Roteiro do caminho de recuperação de senha, ponta a ponta, no navegador:
// o administrador gera o link, uma pessoa sem sessão abre, escolhe a senha e
// entra com ela. É o único caminho de volta para quem perde o acesso.
const { ADMIN } = require("./credenciais.js");
const { chromium } = require("playwright-core");
const BASE = process.env.BASE || "http://localhost:3007";
const API = process.env.API || "http://localhost:8002/api";
const erros = [];

const sufixo = Date.now().toString(36);
const COBAIA = {
  nome: `Teste Senha ${sufixo}`,
  email: `teste.senha.${sufixo}@exemplo.com`,
  senha: "SenhaInicial@2026",
  nova: "SenhaEscolhida@2026",
};

const entrar = async (p, email, senha) => {
  await p.goto(BASE, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  await p.fill('[data-testid="login-email-input"]', email);
  await p.fill('[data-testid="login-password-input"]', senha);
  await p.click('[data-testid="login-submit-button"]');
};

(async () => {
  const b = await chromium.launch({ channel: "chrome", headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  p.on("pageerror", (e) => erros.push("PAGEERROR: " + e.message.slice(0, 140)));

  // O recado tem de estar na tela de login, antes de qualquer sessão: é ali
  // que a pessoa trancada do lado de fora procura o que fazer.
  await p.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="login-form"]', { timeout: 20000 });
  const aviso = await p.textContent('[data-testid="login-esqueci"]').catch(() => null);
  console.log(`${aviso && aviso.includes("administrador") ? "OK " : "FALHA"} login explica como pedir o link`);

  await entrar(p, ADMIN.email, ADMIN.senha);
  await p.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  console.log("OK  login do administrador");

  // Cria a conta cobaia pela própria tela, como um administrador faria.
  await p.goto(`${BASE}/usuarios`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="users-page"]', { timeout: 20000 });
  await p.click('[data-testid="btn-novo-usuario"]');
  await p.fill('[data-testid="user-name-input"]', COBAIA.nome);
  await p.fill('[data-testid="user-email-input"]', COBAIA.email);
  await p.fill('[data-testid="user-password-input"]', COBAIA.senha);
  await p.click('[data-testid="save-user-button"]');
  await p.waitForTimeout(1500);
  const temCobaia = (await p.content()).includes(COBAIA.email);
  console.log(`${temCobaia ? "OK " : "FALHA"} conta de teste criada`);

  // Gera o link na linha dela.
  const linhas = await p.$$('[data-testid^="user-row-"]');
  let indice = -1;
  for (let i = 0; i < linhas.length; i++) {
    if ((await linhas[i].textContent()).includes(COBAIA.email)) indice = i;
  }
  if (indice < 0) throw new Error("não achei a conta de teste na tabela");

  await p.click(`[data-testid="reset-user-${indice}"]`);
  await p.click('[data-testid="confirm-accept"]');
  await p.waitForSelector('[data-testid="reset-link-dialog"]', { timeout: 15000 });
  const link = await p.inputValue('[data-testid="reset-link-valor"]');
  console.log(`${link.includes("/redefinir-senha/") ? "OK " : "FALHA"} link gerado pelo administrador`);
  await p.screenshot({ path: "./shots/80-link-senha.png" });

  // O link é gerado com o FRONTEND_URL do servidor; aqui o painel está em
  // outra porta, então o roteiro usa só o token.
  const token = link.split("/").pop();

  // --- quem recebeu o link: sem sessão nenhuma ---
  const anon = await b.newContext({ viewport: { width: 430, height: 940 } });
  const q = await anon.newPage();
  q.on("pageerror", (e) => erros.push("ANON: " + e.message.slice(0, 140)));
  await q.goto(`${BASE}/redefinir-senha/${token}`, { waitUntil: "networkidle" });
  await q.waitForSelector('[data-testid="reset-form"]', { timeout: 20000 });
  console.log("OK  página de nova senha abre sem sessão |", await q.title());

  // Senhas diferentes: o botão continua travado.
  await q.fill('[data-testid="reset-senha"]', COBAIA.nova);
  await q.fill('[data-testid="reset-repetir"]', "OutraCoisa@2026");
  const travado = await q.getAttribute('[data-testid="reset-submit"]', "disabled");
  console.log(`${travado !== null ? "OK " : "FALHA"} botão trava enquanto as senhas divergem`);

  await q.fill('[data-testid="reset-repetir"]', COBAIA.nova);
  await q.waitForTimeout(250);
  await q.screenshot({ path: "./shots/81-nova-senha.png", fullPage: true });

  const sobra = await q.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  console.log(`${sobra <= 1 ? "OK " : "FALHA"} sem rolagem horizontal no celular (${sobra}px)`);

  await q.click('[data-testid="reset-submit"]');
  await q.waitForSelector('[data-testid="reset-sucesso"]', { timeout: 15000 });
  console.log("OK  senha redefinida");
  await q.screenshot({ path: "./shots/82-senha-ok.png" });

  // --- a senha nova vale, a antiga não ---
  const ctx2 = await b.newContext();
  const r = await ctx2.newPage();
  await entrar(r, COBAIA.email, COBAIA.nova);
  await r.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  console.log("OK  entra com a senha nova");

  const ctx3 = await b.newContext();
  const t = await ctx3.newPage();
  await entrar(t, COBAIA.email, COBAIA.senha);
  await t.waitForTimeout(2500);
  const barrado = !(await t.$('[data-testid="dashboard-page"]'));
  console.log(`${barrado ? "OK " : "FALHA"} senha antiga não entra mais`);

  // --- o link não serve duas vezes ---
  const ctx4 = await b.newContext();
  const u = await ctx4.newPage();
  await u.goto(`${BASE}/redefinir-senha/${token}`, { waitUntil: "networkidle" });
  await u.waitForSelector('[data-testid="reset-form"]', { timeout: 20000 });
  await u.fill('[data-testid="reset-senha"]', "TerceiraSenha@2026");
  await u.fill('[data-testid="reset-repetir"]', "TerceiraSenha@2026");
  await u.click('[data-testid="reset-submit"]');
  await u.waitForSelector('[data-testid="reset-erro"]', { timeout: 15000 });
  console.log("OK  link recusado na segunda tentativa");

  // Limpeza: a conta cobaia existe só por causa deste roteiro.
  await p.goto(`${BASE}/usuarios`, { waitUntil: "networkidle" });
  await p.waitForSelector('[data-testid="users-page"]', { timeout: 20000 });
  const linhas2 = await p.$$('[data-testid^="user-row-"]');
  for (let i = 0; i < linhas2.length; i++) {
    if ((await linhas2[i].textContent()).includes(COBAIA.email)) {
      await p.click(`[data-testid="delete-user-${i}"]`);
      await p.click('[data-testid="confirm-accept"]');
      await p.waitForTimeout(1200);
      break;
    }
  }
  const sumiu = !(await p.content()).includes(COBAIA.email);
  console.log(`${sumiu ? "OK " : "AVISO"} conta de teste removida`);

  console.log("\nerros:", erros.length ? erros.join("\n  ") : "nenhum");
  await b.close();
})().catch(async (e) => {
  console.log("FALHA NO ROTEIRO:", e.message);
  console.log("erros de console:", erros.join("\n  "));
  process.exit(1);
});
