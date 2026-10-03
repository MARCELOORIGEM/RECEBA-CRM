// Cria o usuário da APLICAÇÃO na primeira subida do banco.
//
// O usuário root serve para administrar; a API não deve usá-lo. Este aqui só
// enxerga o banco do CRM e só pode ler e escrever nele — se a credencial da
// API vazar, o estrago fica contido a esse banco.
//
// Roda uma única vez, quando o volume de dados está vazio.
const banco = process.env.MONGO_INITDB_DATABASE;
const usuario = process.env.APP_USER;
const senha = process.env.APP_PASSWORD;

if (!usuario || !senha) {
  print("APP_USER/APP_PASSWORD ausentes — usuário da aplicação não foi criado.");
} else {
  db = db.getSiblingDB(banco);
  db.createUser({
    user: usuario,
    pwd: senha,
    roles: [{ role: "readWrite", db: banco }],
  });
  print(`Usuário '${usuario}' criado com readWrite em '${banco}'.`);
}
