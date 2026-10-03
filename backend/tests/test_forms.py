"""Formulário público de cadastro.

A rota `/api/public/*` responde sem sessão, então cada teste aqui vale por uma
porta trancada: o que a internet consegue ver, o que consegue gravar e o que é
recusado.
"""
import uuid

import pytest
import requests

from .conftest import API, TIMEOUT

# Cliente sem sessão — é assim que o mundo enxerga a rota pública.
anon = requests

# O formulário coleta CPF e conta bancária: a rota exige o aceite do aviso de
# privacidade, do mesmo jeito que a tela exige o visto na caixinha. Os testes
# mandam o aceite porque estão simulando alguém que marcou.
ACEITE = {"_consentimento": True}


def com_aceite(respostas):
    return {**respostas, **ACEITE}


def _campos_restaurante():
    return [
        {"key": "name", "label": "Nome do restaurante", "type": "texto", "required": True},
        {"key": "category", "label": "Tipo de cozinha", "type": "selecao", "required": True,
         "options": ["Pizzaria", "Japonesa"]},
        {"key": "phone", "label": "WhatsApp", "type": "telefone"},
        {"key": "email", "label": "E-mail", "type": "email"},
        {"key": "pedidos_dia", "label": "Pedidos por dia", "type": "numero"},
    ]


@pytest.fixture
def formulario(admin):
    r = admin.post(
        f"{API}/forms",
        json={
            "title": f"Cadastro Teste {uuid.uuid4().hex[:8]}",
            "description": "Formulário de teste",
            "target": "restaurante",
            "fields": _campos_restaurante(),
        },
        timeout=TIMEOUT,
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    yield doc
    # Apaga os cadastros gerados antes do formulário, senão sobram órfãos.
    subs = admin.get(f"{API}/forms/{doc['id']}/submissions", timeout=TIMEOUT)
    if subs.status_code == 200:
        for s in subs.json()["items"]:
            if s.get("created_record_id"):
                admin.delete(
                    f"{API}/restaurants/{s['created_record_id']}",
                    params={"force": "true"},
                    timeout=TIMEOUT,
                )
    # `force` porque o formulário do teste costuma ter respostas, e sem ele a
    # exclusão é (corretamente) recusada com 409.
    admin.delete(f"{API}/forms/{doc['id']}", params={"force": "true"}, timeout=TIMEOUT)


class TestConstrucao:
    def test_slug_sai_do_titulo(self, admin):
        r = admin.post(
            f"{API}/forms",
            json={
                "title": "Cadastro de Restaurantes Parceiros",
                "target": "lead",
                "fields": [{"key": "name", "label": "Nome"}],
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 201
        assert r.json()["slug"] == "cadastro-de-restaurantes-parceiros"
        admin.delete(f"{API}/forms/{r.json()['id']}", timeout=TIMEOUT)

    def test_slug_nao_colide(self, admin):
        base = {"title": "Mesmo Titulo", "target": "lead",
                "fields": [{"key": "name", "label": "Nome"}]}
        a = admin.post(f"{API}/forms", json=base, timeout=TIMEOUT).json()
        b = admin.post(f"{API}/forms", json=base, timeout=TIMEOUT).json()
        assert a["slug"] != b["slug"]
        for f in (a, b):
            admin.delete(f"{API}/forms/{f['id']}", timeout=TIMEOUT)

    def test_slug_nao_muda_ao_renomear(self, admin, formulario):
        """O link já foi distribuído: renomear o formulário não pode quebrá-lo."""
        r = admin.put(
            f"{API}/forms/{formulario['id']}",
            json={"title": "Outro Nome Completamente", "target": "restaurante",
                  "fields": _campos_restaurante()},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert r.json()["slug"] == formulario["slug"]

    def test_exige_campo_name(self, admin):
        r = admin.post(
            f"{API}/forms",
            json={"title": "Sem nome", "target": "restaurante",
                  "fields": [{"key": "phone", "label": "Telefone"}]},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422

    @pytest.mark.parametrize("chave", ["Nome Completo", "nome-completo", "9campo", "", "A" * 60])
    def test_chave_invalida(self, admin, chave):
        r = admin.post(
            f"{API}/forms",
            json={"title": "X", "target": "lead", "fields": [{"key": chave, "label": "X"}]},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422

    def test_chaves_duplicadas(self, admin):
        r = admin.post(
            f"{API}/forms",
            json={"title": "X", "target": "lead",
                  "fields": [{"key": "name", "label": "A"}, {"key": "name", "label": "B"}]},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422

    def test_sem_campos(self, admin):
        r = admin.post(
            f"{API}/forms", json={"title": "X", "target": "lead", "fields": []}, timeout=TIMEOUT
        )
        assert r.status_code == 422

    def test_exige_sessao(self, formulario):
        assert anon.get(f"{API}/forms", timeout=TIMEOUT).status_code == 401
        assert anon.post(f"{API}/forms", json={}, timeout=TIMEOUT).status_code == 401
        assert anon.get(
            f"{API}/forms/{formulario['id']}/submissions", timeout=TIMEOUT
        ).status_code == 401


class TestRotaPublica:
    def test_abre_sem_sessao(self, formulario):
        r = anon.get(f"{API}/public/forms/{formulario['slug']}", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["title"] == formulario["title"]

    def test_nao_expoe_dados_internos(self, formulario):
        """A rota é aberta: nada de destino, autor, contador ou id interno."""
        corpo = anon.get(f"{API}/public/forms/{formulario['slug']}", timeout=TIMEOUT).json()
        assert set(corpo) == {
            "slug", "title", "description", "fields", "success_message",
            # O aviso de privacidade é público de propósito: quem preenche
            # precisa lê-lo antes de aceitar.
            "privacidade",
        }

    def test_slug_inexistente(self):
        assert anon.get(f"{API}/public/forms/nao-existe", timeout=TIMEOUT).status_code == 404

    def test_desativado_recusa(self, admin, formulario):
        admin.patch(f"{API}/forms/{formulario['id']}/active", json={"active": False}, timeout=TIMEOUT)
        try:
            assert anon.get(
                f"{API}/public/forms/{formulario['slug']}", timeout=TIMEOUT
            ).status_code == 410
            assert anon.post(
                f"{API}/public/forms/{formulario['slug']}",
                json={"respostas": {"name": "X"}},
                timeout=TIMEOUT,
            ).status_code == 410
        finally:
            admin.patch(
                f"{API}/forms/{formulario['id']}/active", json={"active": True}, timeout=TIMEOUT
            )


class TestEnvio:
    def _enviar(self, slug, respostas):
        return anon.post(
            f"{API}/public/forms/{slug}",
            json={"respostas": com_aceite(respostas)},
            timeout=TIMEOUT,
        )

    def test_alimenta_o_cadastro(self, admin, formulario):
        r = self._enviar(formulario["slug"], {
            "name": "Cantina do Teste", "category": "Pizzaria",
            "phone": "(11) 90000-0000", "email": "teste@exemplo.com", "pedidos_dia": "40",
        })
        assert r.status_code == 201, r.text
        criado = admin.get(f"{API}/restaurants/{r.json()['id']}", timeout=TIMEOUT).json()
        assert criado["name"] == "Cantina do Teste"
        assert criado["phone"] == "(11) 90000-0000"

    def test_nasce_em_analise(self, admin, formulario):
        """Cadastro vindo da rua não entra ativo: passa por conferência."""
        r = self._enviar(formulario["slug"], {"name": "Novo Parceiro", "category": "Japonesa"})
        criado = admin.get(f"{API}/restaurants/{r.json()['id']}", timeout=TIMEOUT).json()
        assert criado["status"] == "em_analise"
        assert criado["origem"] == "formulario"

    def test_campo_fora_do_modelo_vira_extra(self, admin, formulario):
        r = self._enviar(formulario["slug"], {
            "name": "Com Extra", "category": "Pizzaria", "pedidos_dia": "120",
        })
        criado = admin.get(f"{API}/restaurants/{r.json()['id']}", timeout=TIMEOUT).json()
        assert criado["extra_fields"]["Pedidos por dia"] == 120.0

    def test_ignora_chave_que_o_cliente_inventa(self, admin, formulario):
        """O corpo vem da internet: só as chaves declaradas no formulário valem."""
        r = self._enviar(formulario["slug"], {
            "name": "Só o declarado", "category": "Pizzaria",
            "commission_rate": 0, "status": "ativo", "balance_due": 99999,
        })
        criado = admin.get(f"{API}/restaurants/{r.json()['id']}", timeout=TIMEOUT).json()
        assert criado["status"] == "em_analise", "cliente não pode escolher o status"
        assert criado["commission_rate"] == 15.0, "cliente não pode zerar a comissão"

    @pytest.mark.parametrize(
        "respostas,motivo",
        [
            ({"name": "X"}, "faltou campo obrigatório"),
            ({"name": "X", "category": "Comida Marciana"}, "opção fora da lista"),
            ({"name": "X", "category": "Pizzaria", "email": "nao-e-email"}, "e-mail inválido"),
            ({"name": "X", "category": "Pizzaria", "pedidos_dia": "muitos"}, "número inválido"),
            ({"name": "A" * 3000, "category": "Pizzaria"}, "texto longo demais"),
        ],
    )
    def test_recusa_resposta_invalida(self, formulario, respostas, motivo):
        r = self._enviar(formulario["slug"], respostas)
        assert r.status_code == 422, f"aceitou apesar de: {motivo}"

    def test_isca_descarta_em_silencio(self, admin, formulario):
        """Responder 'você é um robô' só ensina o robô a contornar."""
        antes = admin.get(f"{API}/forms/{formulario['id']}/submissions", timeout=TIMEOUT).json()
        r = self._enviar(formulario["slug"], {
            "name": "Robô", "category": "Pizzaria", "_website": "http://spam.example",
        })
        assert r.status_code == 201, "a resposta precisa parecer um sucesso"
        assert r.json()["id"] is None
        depois = admin.get(f"{API}/forms/{formulario['id']}/submissions", timeout=TIMEOUT).json()
        assert depois["total"] == antes["total"], "nada podia ter sido gravado"

    def test_conta_as_respostas(self, admin, formulario):
        self._enviar(formulario["slug"], {"name": "Contagem", "category": "Pizzaria"})
        atual = admin.get(f"{API}/forms/{formulario['id']}", timeout=TIMEOUT).json()
        assert atual["submissions_count"] >= 1

    def test_nao_exclui_formulario_com_respostas(self, admin, formulario):
        self._enviar(formulario["slug"], {"name": "Histórico", "category": "Pizzaria"})
        r = admin.delete(f"{API}/forms/{formulario['id']}", timeout=TIMEOUT)
        assert r.status_code == 409

    def test_force_exclui_com_historico(self, admin):
        """Saída consciente: o 409 protege de engano, `force` resolve quando a
        intenção é apagar mesmo."""
        criado = admin.post(
            f"{API}/forms",
            json={"title": f"Descartavel {uuid.uuid4().hex[:6]}", "target": "lead",
                  "fields": [{"key": "name", "label": "Nome", "required": True}]},
            timeout=TIMEOUT,
        ).json()
        envio = anon.post(
            f"{API}/public/forms/{criado['slug']}",
            json={"respostas": com_aceite({"name": "Lead do descarte"})},
            timeout=TIMEOUT,
        )
        assert envio.status_code == 201
        lead_id = envio.json()["id"]

        assert admin.delete(f"{API}/forms/{criado['id']}", timeout=TIMEOUT).status_code == 409
        assert admin.delete(
            f"{API}/forms/{criado['id']}", params={"force": "true"}, timeout=TIMEOUT
        ).status_code == 200
        # O cadastro gerado permanece: ele vive no CRM, não no formulário.
        assert admin.get(f"{API}/leads/{lead_id}", timeout=TIMEOUT).status_code == 200
        admin.delete(f"{API}/leads/{lead_id}", timeout=TIMEOUT)


class TestCadastroDeEntregadores:
    """Formulário de recrutamento que a operação usava no Google Forms.

    Os dados bancários deixaram de ser texto solto e viraram campos do
    entregador: é com eles que o repasse sai.
    """

    SLUG = "cadastro-de-entregadores"

    def test_existe_com_as_dez_perguntas(self, admin):
        r = anon.get(f"{API}/public/forms/{self.SLUG}", timeout=TIMEOUT)
        assert r.status_code == 200, "o formulário de entregadores deveria vir na carga inicial"
        corpo = r.json()
        assert corpo["title"] == "Cadastro de Entregadores"
        chaves = [c["key"] for c in corpo["fields"]]
        assert chaves == [
            "name", "cpf", "phone", "vehicle_type", "bank", "bank_agency",
            "account_type", "bank_account", "pix_key_type", "pix_key",
        ]

    def test_instrucoes_chegam_a_quem_preenche(self):
        campos = {
            c["key"]: c for c in anon.get(f"{API}/public/forms/{self.SLUG}", timeout=TIMEOUT).json()["fields"]
        }
        assert "11 números" in campos["cpf"]["help"]
        assert "DDD" in campos["phone"]["help"]
        assert campos["pix_key"]["required"] is False, "a chave PIX é opcional no original"

    def _resposta_valida(self, **extra):
        base = {
            "name": "Entregador de Teste",
            "cpf": "52998224725",
            "phone": "(81) 90000-0000",
            "vehicle_type": "Moto",
            "bank": "Nubank",
            "bank_agency": "0001",
            "account_type": "Conta Corrente",
            "bank_account": "12345678-9",
            "pix_key_type": "CPF",
            "pix_key": "52998224725",
        }
        base.update(ACEITE)
        base.update(extra)
        return base

    def test_alimenta_o_cadastro_do_entregador(self, admin):
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta_valida()},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        try:
            d = admin.get(f"{API}/drivers/{did}", timeout=TIMEOUT).json()
            assert d["cpf"] == "52998224725"
            assert d["bank"] == "Nubank"
            assert d["bank_account"] == "12345678-9"
            assert d["pix_key"] == "52998224725"
            # Os rótulos bonitos viram os valores internos do cadastro.
            assert d["vehicle_type"] == "moto", '"Moto" precisa virar "moto"'
            assert d["account_type"] == "corrente", '"Conta Corrente" -> "corrente"'
            assert d["pix_key_type"] == "cpf"
            # Quem chega pelo formulário não entra disponível para rodar.
            assert d["status"] == "offline"
            assert d["origem"] == "formulario"
        finally:
            admin.delete(f"{API}/drivers/{did}", params={"force": "true"}, timeout=TIMEOUT)

    def test_cpf_aceita_formatado_e_guarda_so_digitos(self, admin):
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta_valida(cpf="529.982.247-25")},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201
        did = r.json()["id"]
        try:
            assert admin.get(f"{API}/drivers/{did}", timeout=TIMEOUT).json()["cpf"] == "52998224725"
        finally:
            admin.delete(f"{API}/drivers/{did}", params={"force": "true"}, timeout=TIMEOUT)

    @pytest.mark.parametrize(
        "campo,valor,motivo",
        [
            ("cpf", "123", "CPF curto"),
            ("cpf", "abcdefghijk", "CPF sem dígitos"),
            ("vehicle_type", "Helicóptero", "modal fora das opções"),
            ("account_type", "Conta Salário", "tipo de conta fora das opções"),
            ("pix_key_type", "Fax", "tipo de chave fora das opções"),
            # "bank" NÃO entra aqui: tem "Outro:" e aceita valor livre de
            # propósito — está coberto em TestOutroNaLista.
        ],
    )
    def test_recusa_valor_invalido(self, campo, valor, motivo):
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta_valida(**{campo: valor})},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422, f"aceitou apesar de: {motivo}"

    def test_chave_pix_pode_ficar_em_branco(self, admin):
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta_valida(pix_key="")},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201
        admin.delete(f"{API}/drivers/{r.json()['id']}", params={"force": "true"}, timeout=TIMEOUT)

    def test_dados_bancarios_exigem_sessao(self, admin):
        """O formulário é público; o que ele gera, não."""
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta_valida()},
            timeout=TIMEOUT,
        )
        did = r.json()["id"]
        try:
            assert anon.get(f"{API}/drivers/{did}", timeout=TIMEOUT).status_code == 401
            assert anon.get(f"{API}/drivers", timeout=TIMEOUT).status_code == 401
        finally:
            admin.delete(f"{API}/drivers/{did}", params={"force": "true"}, timeout=TIMEOUT)


class TestModelosPadrao:
    """Modelos padrão do sistema.

    Ficam numa fonte única (`app/form_templates.py`) que serve tanto a carga
    inicial quanto o construtor da tela. Duplicados em Python e JavaScript, os
    dois lados desandariam no primeiro ajuste feito de um lado só.
    """

    def test_tres_destinos(self, admin):
        r = admin.get(f"{API}/forms/templates", timeout=TIMEOUT)
        assert r.status_code == 200
        assert set(r.json()) == {"entregador", "restaurante", "lead"}

    def test_modelo_de_entregador_tem_as_perguntas_do_processo(self, admin):
        m = admin.get(f"{API}/forms/templates", timeout=TIMEOUT).json()["entregador"]
        assert m["title"] == "Cadastro de Entregadores"
        assert [c["key"] for c in m["fields"]] == [
            "name", "cpf", "phone", "vehicle_type", "bank", "bank_agency",
            "account_type", "bank_account", "pix_key_type", "pix_key",
        ]

    def test_todo_modelo_serve_para_criar_um_formulario(self, admin):
        """O que o construtor recebe tem que passar na validação da API — sem
        isso, o modelo abriria na tela e quebraria só no Salvar."""
        modelos = admin.get(f"{API}/forms/templates", timeout=TIMEOUT).json()
        for destino, m in modelos.items():
            r = admin.post(
                f"{API}/forms",
                json={
                    "title": f"Do modelo {destino} {uuid.uuid4().hex[:6]}",
                    "description": m["description"],
                    "target": m["target"],
                    "success_message": m["success_message"],
                    "fields": m["fields"],
                },
                timeout=TIMEOUT,
            )
            assert r.status_code == 201, f"modelo de {destino} recusado: {r.text}"
            admin.delete(
                f"{API}/forms/{r.json()['id']}", params={"force": "true"}, timeout=TIMEOUT
            )

    def test_todo_modelo_tem_campo_name(self, admin):
        """`name` é o que dá nome ao cadastro gerado; a API exige."""
        for destino, m in admin.get(f"{API}/forms/templates", timeout=TIMEOUT).json().items():
            assert any(c["key"] == "name" for c in m["fields"]), destino

    def test_exige_sessao(self):
        assert anon.get(f"{API}/forms/templates", timeout=TIMEOUT).status_code == 401


class TestOutroNaLista:
    """Opção "Outro:" com escrita livre, como no Google Forms original.

    Uma lista fixa de bancos que não preveja o banco da pessoa a deixa sem como
    responder — e ela desiste do cadastro.
    """

    SLUG = "cadastro-de-entregadores"

    def _resposta(self, **extra):
        base = {
            "name": "Entregador Outro", "cpf": "52998224725", "phone": "(81) 90000-0000",
            "vehicle_type": "Moto", "bank": "Nubank", "bank_agency": "0001",
            "account_type": "Conta Corrente", "bank_account": "12345678-9",
            "pix_key_type": "CPF", "pix_key": "52998224725",
        }
        base.update(ACEITE)
        base.update(extra)
        return base

    def test_banco_e_multipla_escolha_com_outro(self):
        campos = {
            c["key"]: c
            for c in anon.get(f"{API}/public/forms/{self.SLUG}", timeout=TIMEOUT).json()["fields"]
        }
        assert campos["bank"]["type"] == "escolha", "no original é múltipla escolha, não lista"
        assert campos["bank"]["allow_other"] is True
        assert campos["account_type"]["help"], "falta a instrução sobre bancos digitais"

    def test_aceita_banco_fora_da_lista(self, admin):
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta(bank="Banco Cooperativo do Nordeste")},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        try:
            d = admin.get(f"{API}/drivers/{did}", timeout=TIMEOUT).json()
            assert d["bank"] == "Banco Cooperativo do Nordeste"
        finally:
            admin.delete(f"{API}/drivers/{did}", params={"force": "true"}, timeout=TIMEOUT)

    def test_campo_sem_outro_continua_recusando(self):
        """A liberdade é por campo: Modal não tem "Outro", então segue fechado."""
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta(vehicle_type="Patinete")},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422


class TestEdicaoDosDadosDePagamento:
    """Regressão: os dados chegavam pelo formulário mas não havia como
    corrigi-los. Um dígito errado na conta trava o repasse, e ninguém vai pedir
    para o entregador preencher o formulário de novo por causa disso."""

    def test_equipe_corrige_conta_e_pix(self, admin, entregador):
        r = admin.put(
            f"{API}/drivers/{entregador['id']}",
            json={
                "name": entregador["name"],
                "cpf": "529.982.247-25",
                "bank": "Banco Inter",
                "bank_agency": "0001",
                "bank_account": "11112222-3",
                "account_type": "corrente",
                "pix_key_type": "aleatoria",
                "pix_key": "chave-corrigida-999",
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["cpf"] == "52998224725", "o CPF é normalizado também na edição"
        assert d["bank_account"] == "11112222-3"
        assert d["pix_key"] == "chave-corrigida-999"

    def test_cpf_invalido_recusado_na_edicao(self, admin, entregador):
        r = admin.put(
            f"{API}/drivers/{entregador['id']}",
            json={"name": entregador["name"], "cpf": "123"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422

    def test_tipo_de_conta_invalido_recusado(self, admin, entregador):
        r = admin.put(
            f"{API}/drivers/{entregador['id']}",
            json={"name": entregador["name"], "account_type": "salario"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422


class TestConsentimento:
    """Aviso de privacidade (LGPD).

    O formulário pede CPF, conta bancária e chave PIX. Sem o aceite registrado,
    a empresa não tem como mostrar depois com que base coletou esses dados —
    então a rota recusa o envio em vez de gravar e resolver na frente.
    """

    SLUG = "cadastro-de-entregadores"

    def _resposta(self, **extra):
        base = {
            "name": "Teste do Aceite", "cpf": "52998224725",
            "phone": "(81) 90000-0000", "vehicle_type": "Moto",
            "bank": "Nubank", "bank_agency": "0001", "account_type": "Conta Corrente",
            "bank_account": "12345678-9", "pix_key_type": "CPF", "pix_key": "52998224725",
        }
        base.update(extra)
        return base

    def test_o_aviso_chega_a_quem_preenche(self):
        """De nada adianta exigir o aceite sem dizer do que se trata."""
        r = anon.get(f"{API}/public/forms/{self.SLUG}", timeout=TIMEOUT)
        assert r.status_code == 200
        privacidade = r.json()["privacidade"]
        assert privacidade["texto"], "o texto do aviso precisa vir junto do formulário"

    def test_recusa_envio_sem_aceite(self):
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": self._resposta()},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422, "sem aceite, o cadastro não pode ser gravado"
        assert "privacidade" in r.json()["detail"].lower()

    def test_registra_o_aceite_na_resposta(self, admin):
        """O aceite fica guardado com a resposta, não só com o envio: é a prova
        de que a pessoa viu o aviso naquele momento."""
        r = anon.post(
            f"{API}/public/forms/{self.SLUG}",
            json={"respostas": {**self._resposta(), **ACEITE}},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        try:
            forms = admin.get(f"{API}/forms", timeout=TIMEOUT).json()
            itens = forms["items"] if isinstance(forms, dict) else forms
            form = next(f for f in itens if f["slug"] == self.SLUG)
            envios = admin.get(
                f"{API}/forms/{form['id']}/submissions", timeout=TIMEOUT
            ).json()["items"]
            registro = next(e for e in envios if e.get("created_record_id") == did)
            assert registro["consentimento"]["aceito"] is True
            assert registro["consentimento"]["texto"], "guarde o texto aceito, não só o sim"
        finally:
            admin.delete(f"{API}/drivers/{did}", params={"force": "true"}, timeout=TIMEOUT)
