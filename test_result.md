#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  "olhe tudo e veja o que precisa melhorar, lembre tem que ser um CRM, abra o
  sistema analise e melhore em todos os aspecto."
  Auditoria completa do sistema e melhorias em todas as frentes: segurança,
  integridade de dados, regras de negócio, funcionalidades de CRM, interface,
  acessibilidade, testes e documentação.

backend:
  - task: "Segurança: cadastro público fechado, RBAC, rate limit, chaves com hash"
    implemented: true
    working: true
    file: "app/routers/auth.py, app/deps.py, app/routers/integrations.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Falhas confirmadas por chamada real contra a API antiga:
            POST /auth/register era público e aceitava role:"admin" (200);
            gestor criava chave de produção e excluía cadastros (200);
            chaves de API guardadas e devolvidas em texto puro na listagem.
            Agora: register desligado por padrão e sem role vindo do cliente;
            exclusões, chaves, usuários e auditoria restritos ao admin; chave
            só como hash SHA-256, valor exibido uma única vez; limite de
            tentativas de login por e-mail+IP (429); flags do cookie derivadas
            do esquema de FRONTEND_URL (Secure fixo descartava a sessão em
            HTTP local).

  - task: "Validação de entrada e 404 em recursos inexistentes"
    implemented: true
    working: true
    file: "app/models.py, app/repo.py, app/main.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Antes a API aceitava comissão -50%, status "voando", valor -999 e
            data "nao-e-data", todos com 200; PUT/DELETE em id inexistente
            respondiam 200 "Removido". Agora: Literal/ge/le/date no Pydantic,
            get_or_404 em todas as rotas e handler que devolve o erro de
            validação como frase em português, no lugar do array cru que o
            frontend exibia como JSON.

  - task: "Motor financeiro: entrega alimenta saldos e contadores"
    implemented: true
    working: true
    file: "app/financials.py, app/routers/orders.py, app/routers/payments.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            total_deliveries, balance_due e orders_month eram números fixos do
            seed (random.randint) e nada no sistema os movia. Agora a entrega
            lança repasse e comissão pela regra do contrato ativo, de forma
            idempotente (financials_applied) e reversível; liquidar o pagamento
            baixa o saldo do credor e o estorno devolve. orders_month passou a
            ser calculado na leitura — gravado no documento, nunca virava o mês.

  - task: "Modelo relacional por id e fluxo de status do pedido"
    implemented: true
    working: true
    file: "app/routers/orders.py, app/routers/restaurants.py, app/routers/drivers.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Vínculos eram por nome em texto; renomear um cadastro deixava o
            histórico apontando para um nome inexistente. Agora por id, com
            propagação do nome para pedidos, contratos e pagamentos. Código do
            pedido usa contador atômico (antes count_documents+1, que duplicava
            em corrida). Transições de status validadas e entrega exige
            entregador atribuído.

  - task: "CRM: funil de vendas, atividades, timeline, auditoria e busca global"
    implemented: true
    working: true
    file: "app/routers/leads.py, app/routers/activities.py, app/routers/misc.py, app/audit.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            O sistema só sabia lidar com quem já era cliente — não havia funil,
            follow-up nem histórico de relacionamento. Adicionados: funil com
            histórico de etapa, motivo de perda obrigatório e conversão de lead
            em restaurante; atividades (tarefas com prazo e interações
            registradas); timeline por cadastro; trilha de auditoria com diff e
            redação de segredos; busca global cruzando as coleções.

  - task: "Dashboard com métricas corretas"
    implemented: true
    working: true
    file: "app/routers/dashboard.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            entregas_hoje contava a base inteira; taxa_sucesso dividia entregues
            pelo total, então caía sozinha a cada pedido ainda em rota;
            "faturamento" somava o valor das compras, que é do restaurante e não
            receita da Miliano. Agora: recorte por dia, taxa sobre pedidos
            finalizados, receita = comissão, mais tendência de 14 dias, margem,
            ticket médio, resumo do funil e da agenda.

  - task: "Reestruturação, índices, paginação e migração de dados"
    implemented: true
    working: true
    file: "app/, server.py, app/db.py, app/seed.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            server.py de 612 linhas dividido em app/ por domínio (server.py
            segue como ponto de entrada). Índices em todas as coleções
            filtradas; listagens paginadas com busca e filtro no servidor (antes
            to_list(1000) e filtro no navegador). Migração de startup converte
            vínculos para id, saneia registros inválidos herdados e recalcula os
            saldos a partir dos pedidos reais, uma única vez, marcada em
            `migrations`.

frontend:
  - task: "Sessão: renovação automática e expiração tratada"
    implemented: true
    working: true
    file: "src/lib/api.js, src/context/AuthContext.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            /auth/refresh existia no backend mas nada no frontend chamava:
            passados 60 minutos, toda tela falhava em silêncio até recarregar a
            página. Interceptor 401 com fila de requisições em espera e aviso ao
            usuário quando a sessão realmente acaba.

  - task: "Telas novas: Funil (kanban) e Atividades"
    implemented: true
    working: true
    file: "src/pages/Pipeline.jsx, src/pages/Activities.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Kanban com arrastar entre etapas, motivo de perda obrigatório e
            conversão em cliente; agenda com abas atrasadas/hoje/próximas e
            contador de atrasadas no menu lateral.

  - task: "Confirmação em ações destrutivas e RBAC na interface"
    implemented: true
    working: true
    file: "src/components/ConfirmDialog.jsx, todas as páginas"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            A lixeira apagava na hora, sem pergunta e sem desfazer. Agora há
            confirmação, com segunda confirmação quando o backend responde 409
            (ex.: restaurante com pedidos no histórico). Ações de admin ficam
            escondidas do gestor.

  - task: "Tema, acessibilidade, responsivo e paleta de busca (Ctrl+K)"
    implemented: true
    working: true
    file: "public/index.html, src/components/Layout.jsx, CommandPalette.jsx, Ui.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            A classe dark estava numa div interna: componentes Radix montam em
            portal no body e a paleta de busca abria branca sobre o app escuro
            (confirmado em captura de tela). Movida para o <html>. Botões de
            ícone ganharam aria-label, inputs ganharam label associado,
            DialogTitle oculto adicionado à paleta, ErrorBoundary por rota,
            página 404 própria e verificação de ausência de rolagem horizontal
            em 390px.

  - task: "Conta própria, edição de pedido, funil por teclado e relatório completo"
    implemented: true
    working: true
    file: "src/components/AccountDialog.jsx, src/pages/Orders.jsx, src/pages/Pipeline.jsx, src/lib/api.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Segunda passada, lacunas encontradas na revisão:
            (1) "Minha conta" no rodapé do menu, para trocar a própria senha e o
            nome — antes um gestor ficava preso à senha de cadastro;
            (2) edição de pedido: a API tinha PUT /orders/{id}, mas a tela não
            usava, então corrigir um endereço exigia excluir e refazer. O select
            passou a listar também restaurantes não-ativos (um pedido antigo de
            restaurante suspenso abria com o campo vazio) e o botão desabilitado
            agora diz o que falta, em vez de ficar morto sem explicação;
            (3) menu "mover para" em cada cartão do funil: arrastar não funciona
            por teclado nem com leitor de tela;
            (4) o relatório pedia 200 registros e usava como se fosse o conjunto
            completo, truncando em silêncio; agora percorre todas as páginas e
            avisa se o período for maior que o teto.

  - task: "Listagens paginadas e relatórios com período real"
    implemented: true
    working: true
    file: "src/pages/*.jsx, src/components/Ui.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Busca, filtro e paginação passaram para o servidor. Em Relatórios, o
            período agora vale também para a tabela financeira (antes ela
            ignorava as datas escolhidas) e o CSV sai com separador ";", BOM e
            campos escapados, para abrir direto no Excel em português.

  - task: "Fuso horário do negócio nos recortes de 'hoje'"
    implemented: true
    working: true
    file: "app/tempo.py, app/routers/dashboard.py, app/routers/activities.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Segunda passada. Todo recorte de "hoje" usava meia-noite UTC. Em São
            Paulo (UTC-3) o dia virava às 21h: entregas entre 21h e meia-noite,
            o pico do delivery, caíam no dia seguinte do painel, o gráfico "por
            hora" saía deslocado em 3 horas e uma tarefa marcada para as 22h
            aparecia em "Próximas" em vez de "Hoje". Agora tudo passa por
            app/tempo.py, no fuso TIMEZONE (padrão America/Sao_Paulo), inclusive
            os agrupamentos por dia e hora no Mongo. Fallback para UTC com aviso
            caso o pacote tzdata não esteja presente.

  - task: "Estorno de entrega devolvia menos do que havia lançado"
    implemented: true
    working: true
    file: "app/financials.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Defeito introduzido na primeira rodada, encontrado na revisão e
            reproduzido: `apply_delivery` creditava o entregador achado pelo
            NOME quando o pedido não tinha `driver_id`, mas `revert_delivery` só
            debitava quando o id existia. Medido: saldo 0 -> 20 -> 20 e entregas
            0 -> 1 -> 1, ou seja, o saldo inflava de forma permanente a cada
            pedido migrado sem id. O pedido agora grava quem foi creditado e
            sobre qual valor (credited_driver_id, credited_restaurant_id,
            credited_amount) e o estorno devolve exatamente isso — inclusive se
            o valor do pedido for editado depois da entrega.

  - task: "Coerência das abas da agenda"
    implemented: true
    working: true
    file: "app/routers/activities.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            `scope="hoje"` não tinha limite inferior: a aba "Hoje" devolvia
            também tudo que estava atrasado, e mostrava número diferente do
            contador da própria aba, que vinha de /activities/summary. Os dois
            passaram a usar os mesmos limites; testes garantem que "atrasadas",
            "hoje" e "próximas" não se sobrepõem.

  - task: "Troca da própria senha e seed que a desfazia"
    implemented: true
    working: true
    file: "app/routers/auth.py, app/seed.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Não havia rota para o usuário trocar a própria senha — só a edição
            de usuários, restrita ao administrador (medido: gestor recebia 403
            ao tentar trocar a própria senha). Criados PUT /auth/me e
            POST /auth/password, com verificação da senha atual. Ao implementar,
            apareceu um conflito: seed_users reescrevia a senha das contas do
            .env a cada boot, o que desfaria a troca no próximo restart. A senha
            do .env passou a valer somente na criação da conta.

  - task: "Desempenho do painel e higiene do login_attempts"
    implemented: true
    working: true
    file: "app/routers/dashboard.py, app/routers/auth.py, app/db.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            /dashboard/stats levava 511 ms, quase tudo no laço que fazia 28
            count_documents para a tendência de 14 dias; virou uma agregação e
            caiu para ~216 ms. O índice TTL de login_attempts nunca apagava
            nada, porque created_at era gravado como texto ISO e o TTL do Mongo
            só expira campo BSON Date: passou a ser datetime, e a migração
            limpa os registros antigos em texto.

  - task: "Rebranding: Receba -> Miliano"
    implemented: true
    working: true
    file: "todo o projeto, app/seed.py (migração de conta)"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Troca por token exato, nunca por 'receba' solto: o português tem
            'recebe', 'receber', 'a receber' e 'recebido' espalhados pela
            interface e pelos comentários. A senha ADMIN_PASSWORD, que por
            coincidência é "<senha do admin>", foi protegida e não mudou.
            45 substituições em 22 arquivos: marca na interface, título da aba,
            PDF exportado, docstrings, logger, prefixo das chaves de API
            (rcb_ -> rcp_) e URLs de exemplo dos webhooks.
            O e-mail do gestor mudou para <e-mail do gestor>, por
            decisão do usuário. A conta existente é renomeada por migração
            guardada em seed.py (migrar_emails), preservando senha, perfil e
            histórico — sem ela, mudar MANAGER_EMAIL no .env faria o seed criar
            uma conta nova e deixar a antiga órfã.
            Achado durante a verificação: a tela de login definia o título da
            aba e ninguém o devolvia, então o navegador continuava anunciando
            "Entrar" já dentro do sistema. O título passou a acompanhar a rota.
            Fora do escopo por decisão: a conta admin@receba.com ("Admin
            Receba"), que existia na base antes deste trabalho e não está no
            .env — renomeá-la mudaria o login de alguém sem confirmação.

  - task: "Formulário público personalizável de cadastro"
    implemented: true
    working: true
    file: "app/routers/forms.py, app/routers/public.py, src/pages/Forms.jsx, src/pages/PublicForm.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            A entrada de restaurantes e entregadores era 100% digitação da
            equipe. Agora o gestor monta o formulário (campos, tipos, ordem,
            obrigatoriedade, opções), copia o link /f/<slug> e a resposta entra
            direto no CRM, no destino escolhido: lead, restaurante ou entregador.

            A rota pública ficou em routers/public.py, separada de propósito:
            tudo em forms.py exige sessão, tudo lá é aberto à internet. O que
            protege a rota aberta, cada item com teste próprio:
            - devolve só título, descrição e campos — nada de destino, autor,
              contador ou id interno;
            - valida cada resposta contra a definição do campo e IGNORA
              qualquer chave que o cliente invente, então ninguém escolhe o
              próprio status nem zera a comissão pelo corpo da requisição;
            - limite de 10 envios por IP por hora;
            - campo-isca invisível: preenchido, a resposta PARECE sucesso e não
              grava nada (dizer "você é um robô" só ensina o robô a contornar);
            - formulário desativado responde 410 para ver e para responder.

            Decisões de modelagem: o slug não muda quando o título é editado,
            porque o link já foi distribuído; quem chega pelo formulário nasce
            em análise/offline, nunca ativo, e leva origem="formulario"; campo
            com chave fora do modelo vira informação extra em vez de ser
            descartado. Excluir formulário com respostas dá 409, com saída
            `force` — o mesmo padrão já usado em restaurantes e entregadores.

  - task: "Identidade visual Miliano Business Solutions"
    implemented: true
    working: true
    file: "tailwind.config.js, src/index.css, src/components/Logo.jsx, src/pages/Login.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Rebranding a partir do logo enviado: grafite quente, dourado e prata.

            As rampas `slate` e `orange` do Tailwind foram REDEFINIDAS em
            tailwind.config.js, com comentário explicando: a interface usava
            essas classes em ~600 lugares e renomear uma a uma seria churn puro,
            com risco de erro e nenhum ganho — o tema troca o valor por trás do
            nome. Mais 39 cores fixas de gráfico e fundo trocadas à mão, porque
            não passam pelo Tailwind.

            Componente Logo reproduz os três elementos do impresso: arco
            dourado, letreiro cromado em fonte script e assinatura prata/dourada.
            O arco é centrado no LETREIRO, não no bloco inteiro — centrado no
            bloco ele descia e cruzava "BUSINESS SOLUTIONS" (corrigido na
            verificação visual).

            Tela de login refeita: brasa dourada difusa no fundo, reflexo que
            acompanha o cursor sobre o cartão, ícones que reagem ao foco do
            campo e destaques em cascata. Toda animação respeita
            prefers-reduced-motion, por regra global no index.css.

            Fora do escopo por decisão: o e-mail <e-mail do gestor>
            (credencial de login) e o handle do Instagram — ambos dependem de
            domínio e conta reais que só o dono da marca sabe.

  - task: "Formulário de entregadores vindo do Google Forms"
    implemented: true
    working: true
    file: "app/seed.py, app/models.py, app/routers/public.py, src/pages/PublicForm.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            O usuário passou o link do Google Forms que a operação já usava.
            As 10 perguntas foram lidas de lá e reproduzidas exatamente: mesmo
            texto, ordem, obrigatoriedade, opções e instruções.

            CPF, banco, agência, tipo de conta, número da conta, tipo de chave
            PIX e chave PIX viraram CAMPOS DO ENTREGADOR, não texto solto em
            extra_fields: é com eles que o repasse sai, e aparecem no detalhe do
            cadastro. O formulário é público; ler o que ele gera exige sessão.

            Tipos de campo novos: `escolha` (múltipla escolha em botões, melhor
            que lista para 2-4 opções, ainda mais no celular) e `cpf` (guarda só
            os 11 dígitos, aceitando o valor formatado). Os rótulos escolhidos
            pela pessoa são traduzidos para os valores internos — "Conta
            Corrente" -> "corrente", "Moto" -> "moto".

            Bug encontrado na verificação: `maxLength={11}` no input de CPF
            cortava "529.982.247-25" em 11 CARACTERES antes da máscara remover
            os pontos, sobrando 9 dígitos. O corte passou a ser só depois.

            A carga é travada pelo SLUG, não por "coleção vazia". Isso importou
            na prática: o usuário já tinha criado o formulário "CADASTRO RECIFE"
            (com 1 resposta recebida), e ele permaneceu intacto — o de
            entregadores entrou ao lado.

  - task: "Parceria Keeta e navegação no topo"
    implemented: true
    working: true
    file: "src/components/Keeta.jsx, src/components/Layout.jsx, src/pages/Dashboard.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Parceria oficial Keeta em três pontos, com o verde e o amarelo da
            marca: selo na barra do topo, faixa no dashboard (curvas verde e
            amarela como no banner impresso) e cabeçalho do formulário público.
            As duas cores ficam RESTRITAS a esses pontos — espalhá-las pela
            interface apagaria as duas paletas; o dourado segue sendo a cor do
            sistema.

            A barra lateral virou navegação no topo, em duas linhas: marca +
            parceria + busca + conta na primeira, itens na segunda. Os 256px da
            lateral voltaram para o conteúdo (medido: main passou a usar os
            1440px da janela). Rótulos encurtaram ("Contratos & Pagamentos" ->
            "Financeiro") porque na horizontal nome comprido rouba espaço dos
            outros. "Sair" e "Minha conta" foram para um menu da conta, que
            fecha com clique fora e com Esc.

metadata:
  created_by: "main_agent"
  version: "4.0"
  test_sequence: 9
  run_ui: true

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Auditoria e reescrita concluídas e verificadas com o sistema rodando.

        Segunda passada de auditoria concluída: 5 defeitos encontrados no código
        da primeira rodada (estorno assimétrico, fuso em UTC, abas da agenda
        incoerentes, índice TTL inerte, painel lento) e 4 lacunas preenchidas
        (senha própria, edição de pedido, funil por teclado, relatório completo).
        Cada defeito foi reproduzido antes da correção e travado por teste.

        Backend: 149 testes pytest passando (tests/backend_test.py e
        tests/test_new_features.py, fixtures em tests/conftest.py). Boa parte é
        teste de regressão — cada um trava um comportamento que a versão
        anterior errava, com o motivo escrito no próprio teste. A suíte não
        deixa resíduo no banco (verificado contando documentos antes e depois).

        Frontend: build de produção compila sem erro e quatro roteiros em Chrome
        headless cobre login, as 10 telas, busca global, criação de lead e
        atividade, confirmação de exclusão, registro de interação na timeline,
        layout em 390px e o perfil gestor sem as ações de admin. Nenhum erro de
        console originado da aplicação.

        Para rodar os testes localmente:
          REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/ -q

        Pendente de decisão do dono do repositório: backend/.env estava
        versionado com JWT_SECRET e senhas. Foi adicionado ao .gitignore, mas se
        já houve commit, os segredos continuam recuperáveis no histórico e
        precisam ser rotacionados.

    - agent: "main"
      message: |
        Rodada de preparação para produção — "faça tudo que está faltando,
        deixe completo e seguro".

        BANCO DE DADOS (resposta ao que foi perguntado): sim, precisa, e é
        MongoDB 6 ou 7. Um banco, um usuário com readWrite só nele, 10 GB de
        disco, 2 GB de RAM, backup diário, e a porta 27017 nunca exposta. Não
        é preciso criar coleção nem rodar migração à mão: a API cria índices,
        migra e semeia sozinha no primeiro boot. As três formas de ter esse
        banco (compose, Atlas M10, Mongo existente) estão em PRODUCAO.md, com
        a conta de disco e o passo a passo.

        O QUE FOI FECHADO NESTA RODADA
        - Redefinição de senha ponta a ponta: rota POST /senha/link/{uid}
          (admin) e POST /senha/redefinir (pública), página
          /redefinir-senha/:token, botão na tela de Usuários e o recado na tela
          de login. Token só em hash no banco, 30 min, uso único, gerar outro
          invalida o anterior.
        - Aceite do aviso de privacidade no formulário público. O backend já
          exigia; faltava a caixa na tela — sem ela, o formulário estava
          QUEBRADO para quem fosse se cadastrar.
        - Exclusão de uma resposta recebida (DELETE
          /forms/{fid}/submissions/{sid}, admin) com botão na tela. Existe por
          causa do pedido de exclusão da LGPD: a resposta guarda CPF e conta, e
          apagar só o cadastro deixava essa cópia para trás.
        - Apagar formulário com histórico pela tela. O backend devolvia 409
          dizendo "confirme a exclusão definitiva" e a tela não tinha como
          confirmar: era um beco sem saída.
        - Scripts de terceiros removidos do index.html (PostHog apontando para
          ap.emergent.sh, assets.emergent.sh e um injetor de challenge da
          Cloudflare). Essa página serve o formulário onde o entregador digita
          CPF e conta bancária. Entraram no lugar favicon, manifest, robots.txt
          e meta noindex.
        - MAX_ENVIOS_POR_IP virou configuração. O teto fixo de 10/hora trava
          uma ação de rua, onde dezenas se cadastram pela mesma rede.
        - Opção "Outro" duplicada no campo Banco: a lista trazia "Outro" e o
          allow_other desenhava "Outro:" — dois botões com o mesmo nome, um
          deles inerte. Corrigido no modelo e no formulário que estava no ar.
        - backend/.env e frontend/.env apontavam para a URL de preview do
          andaime, que não existe mais; CORS_ORIGINS era "*", que o navegador
          recusa junto com cookie de sessão.

        TESTES
        - 183 testes pytest passando, 1 pulado (o do teto por IP, que se pula
          quando MAX_ENVIOS_POR_IP está alto; verificado à parte com teto 4).
          Novo arquivo tests/test_producao.py cobre link de senha, entrada de
          eventos do marketplace, teto por IP e exclusão de resposta.
        - 7 roteiros de navegador (~79 conferências) agora versionados em
          tests_e2e/, com runner e README. Rodados do começo ao fim: todos
          passam e a base fica exatamente como estava antes — contado
          documento a documento.

        DEFEITOS ENCONTRADOS NOS PRÓPRIOS TESTES (e corrigidos)
        - Os roteiros não limpavam o que criavam: entregador, lead, atividade,
          interação, formulário e resposta iam se acumulando no CRM real a cada
          rodada. Pior: nomes fixos faziam uma rodada "passar" olhando para o
          resíduo da anterior — era o caso do "criar atividade", que só passava
          porque encontrava os Follow-up das rodadas antigas.
        - test_cnpj_duplicado usava CNPJ fixo e colidia com o roteiro 03.
        - A conferência "aparece na aba Hoje" dependia da hora: o prazo padrão
          da tela é "daqui a uma hora" e, rodando às 23h, cai legitimamente em
          "Próximas". O sistema estava certo; o roteiro é que estava errado.

        OBSERVAÇÃO DE AMBIENTE: a porta 8001 está ocupada desde 07/09 por outro
        backend do usuário (C:\Users\DELL\Desktop\RECEBA -SITE), ligado em
        127.0.0.1. A verificação desta rodada rodou com o CRM em 8002 e o build
        servido em 3010. Nada foi encerrado no outro projeto.
