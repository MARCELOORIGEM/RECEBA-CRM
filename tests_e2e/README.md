# Roteiros de navegador

Sete roteiros que abrem o sistema num Chrome de verdade e conferem o que o
pytest não alcança: a tela desenha, o clique faz o que promete, o dado entra e
aparece do outro lado.

```bash
cd tests_e2e && npm install                     # uma vez
BASE=http://localhost:3000 ADMIN_EMAIL=... ADMIN_PASSWORD=... MANAGER_EMAIL=... MANAGER_PASSWORD=... ./rodar.sh
```

`BASE` é o endereço do **painel**. Os roteiros dirigem o Chrome instalado na
máquina (`channel: "chrome"`), sem baixar navegador.

| Roteiro | O que cobre |
|---|---|
| `01-painel.js` | login, todas as telas, busca global, criar lead e atividade, linha do tempo, celular, o que o gestor não vê |
| `02-gestor.js` | sessão do gestor, troca da própria senha, editar pedido, mover lead sem arrastar, navegação por teclado |
| `03-formulario.js` | criar formulário, abrir o link público sem sessão, enviar e ver o cadastro chegar "em análise" |
| `04-keeta.js` | formulário de entregadores no celular, máscara de CPF, menu no topo, parceria Keeta, dados bancários no cadastro |
| `05-modelos.js` | construtor: modelo padrão, editar, excluir, repor e trocar de destino |
| `06-banco-outro.js` | "Outro:" no campo Banco — escrita livre chegando ao cadastro e a correção pela equipe |
| `07-nova-senha.js` | link de nova senha ponta a ponta: administrador gera, pessoa redefine, senha antiga morre, link não serve duas vezes |

Cada roteiro cria o que precisa e **apaga no fim**. As capturas ficam em
`tests_e2e/shots/`.

> Os roteiros escrevem no banco apontado pelo painel. Rode contra um ambiente de
> teste, não contra a base da operação.

## Credenciais

Os roteiros liam o e-mail e a senha reais do administrador, escritos dentro de
cada arquivo — sete cópias da conta do sistema, que num repositório publicado
qualquer um lê. Agora saem de `credenciais.js`, nesta ordem:

1. as variáveis `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `MANAGER_EMAIL` e
   `MANAGER_PASSWORD` do ambiente;
2. o `backend/.env` desta instalação, que já existe e já é ignorado pelo Git.

Na prática, **não é preciso configurar nada** para rodar local: o `.env` do
backend responde. Faltando os dois, o script para com a mensagem dizendo o que
preencher, em vez de falhar na tela de login com "credenciais inválidas" — que
manda procurar o bug no lugar errado.

Aponte sempre para a **sua instalação local**, nunca para produção: alguns
roteiros criam e apagam dados.
