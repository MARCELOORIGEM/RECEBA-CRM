// Credenciais dos roteiros de navegador.
//
// Estavam escritas dentro de cada roteiro — o e-mail e a senha REAIS do
// administrador, repetidos em sete arquivos. Num repositório publicado isso é
// a conta do sistema entregue a quem clonar, e trocar a senha significaria
// caçar a string em sete lugares.
//
// Agora vêm do ambiente, com um padrão que só serve para instalação local de
// desenvolvimento:
//
//   ADMIN_EMAIL=... ADMIN_PASSWORD=... ./rodar.sh
//
// Os padrões batem com os de backend/.env.example, não com os de produção.
const ADMIN = {
  email: process.env.ADMIN_EMAIL || "admin@local.test",
  senha: process.env.ADMIN_PASSWORD || "SenhaLocal@2026",
};

const GESTOR = {
  email: process.env.MANAGER_EMAIL || "gestor@local.test",
  senha: process.env.MANAGER_PASSWORD || "SenhaLocal@2026",
};

module.exports = { ADMIN, GESTOR };
