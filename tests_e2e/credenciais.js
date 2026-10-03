// Credenciais dos roteiros de navegador.
//
// Estavam escritas dentro de cada roteiro — o e-mail e a senha REAIS do
// administrador, repetidos em sete arquivos. Num repositório publicado isso é
// a conta do sistema entregue a quem clonar, e trocar a senha significaria
// caçar a string em sete lugares.
//
// A ordem de busca é: variável de ambiente primeiro (é assim que o CI manda
// as contas dele), depois o backend/.env desta instalação — que já existe, já
// é ignorado pelo Git, e evita ter de exportar quatro variáveis para rodar a
// suíte local.
const fs = require("fs");
const path = require("path");

const lerEnvDoBackend = () => {
  const arquivo = path.join(__dirname, "..", "backend", ".env");
  try {
    return Object.fromEntries(
      fs
        .readFileSync(arquivo, "utf8")
        .split(/\r?\n/)
        .filter((linha) => /^\s*[A-Z_]+\s*=/.test(linha))
        .map((linha) => {
          const i = linha.indexOf("=");
          const chave = linha.slice(0, i).trim();
          // O arquivo guarda os valores entre aspas; o navegador não quer
          // aspas dentro do campo de senha.
          const valor = linha
            .slice(i + 1)
            .trim()
            .replace(/^["']|["']$/g, "");
          return [chave, valor];
        })
    );
  } catch {
    // Sem backend/.env (CI, ou máquina só com o painel) as variáveis de
    // ambiente respondem sozinhas.
    return {};
  }
};

const env = lerEnvDoBackend();
const ler = (chave) => process.env[chave] || env[chave] || "";

const ADMIN = { email: ler("ADMIN_EMAIL"), senha: ler("ADMIN_PASSWORD") };
const GESTOR = { email: ler("MANAGER_EMAIL"), senha: ler("MANAGER_PASSWORD") };

for (const [nome, conta] of [["ADMIN", ADMIN], ["GESTOR", GESTOR]]) {
  if (!conta.email || !conta.senha) {
    // Falhar aqui, com o motivo, em vez de na tela de login com "credenciais
    // inválidas" — que manda procurar o bug no lugar errado.
    console.error(
      `\n${nome} sem credencial. Preencha backend/.env ou exporte ` +
        `${nome === "ADMIN" ? "ADMIN_EMAIL/ADMIN_PASSWORD" : "MANAGER_EMAIL/MANAGER_PASSWORD"}.\n`
    );
    process.exit(1);
  }
}

module.exports = { ADMIN, GESTOR };
