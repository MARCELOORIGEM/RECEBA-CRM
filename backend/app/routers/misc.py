"""Busca global, timeline por cadastro, auditoria e saúde da API."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import pg, repo
from ..deps import get_current_user, require_admin
from ..permissoes import pode

router = APIRouter(tags=["geral"])

# (tabela, colunas pesquisadas, tipo, campo do título, campos do subtítulo,
#  rota, módulo exigido)
ALVOS_DA_BUSCA = [
    ("restaurants", ["name", "cnpj", "contact_person", "phone"],
     "Restaurante", "name", ["category", "status"], "/restaurantes", "restaurantes"),
    ("drivers", ["name", "plate", "phone"],
     "Entregador", "name", ["vehicle_type", "status"], "/entregadores", "entregadores"),
    ("orders", ["code", "customer_name", "restaurant_name"],
     "Pedido", "code", ["restaurant_name", "customer_name"], "/pedidos", "pedidos"),
    ("leads", ["name", "codigo_externo", "contact_name", "bairro", "city"],
     "Lead", "name", ["codigo_externo", "bairro", "bd_nome"], "/funil", "funil"),
    ("payments", ["creditor"],
     "Pagamento", "creditor", ["status", "due_date"], "/contratos-pagamentos", "financeiro"),
]

# Tipo de cadastro da linha do tempo -> módulo que dá acesso a ele.
MODULO_DA_ENTIDADE = {
    "lead": "funil", "restaurante": "restaurantes", "entregador": "entregadores",
    "pedido": "pedidos",
}


@router.get("/health")
async def health():
    """Ping sem autenticação, para load balancer e monitoramento."""
    try:
        await pg.valor("SELECT 1")
        return {"status": "ok", "database": "up"}
    except Exception:
        return {"status": "degraded", "database": "down"}


@router.get("/search")
async def global_search(q: str = Query("", min_length=0), user: dict = Depends(get_current_user)):
    """Busca única sobre todo o CRM — alimenta o atalho Ctrl/⌘+K do painel."""
    term = q.strip()
    if len(term) < 2:
        return {"results": []}

    # Só onde o usuário tem acesso: a busca não pode virar a porta dos fundos
    # para o cadastro que o administrador escondeu dele. E abre direto na
    # tela, então só vale o que ele abre de verdade (módulo próprio, não a
    # leitura de apoio).
    alvos = [a for a in ALVOS_DA_BUSCA if pode(user, a[6], escrita=True)]
    # As tabelas em paralelo: em sequência, a 200 ms cada, o atalho de busca
    # levaria um segundo para responder a cada tecla.
    achados = await asyncio.gather(*(
        repo.listar(tabela, repo.filtro(tabela).busca(term, campos), limite=5)
        for tabela, campos, *_ in alvos
    ))

    results: list[dict] = []
    for (_, _, tipo, titulo, sub, rota, _), docs in zip(alvos, achados):
        for d in docs:
            results.append({
                "tipo": tipo,
                "id": d["id"],
                "titulo": d.get(titulo, ""),
                "subtitulo": " • ".join(str(d.get(f, "")) for f in sub if d.get(f)),
                "rota": rota,
            })
    return {"results": results}


@router.get("/timeline/{entity_type}/{entity_id}")
async def timeline(entity_type: str, entity_id: str, user: dict = Depends(get_current_user)):
    """Linha do tempo de um cadastro: interações, tarefas e alterações."""
    modulo = MODULO_DA_ENTIDADE.get(entity_type)
    if not modulo or not pode(user, modulo):
        raise HTTPException(status_code=403, detail="Sem acesso a este cadastro.")
    atividades, logs = await asyncio.gather(
        repo.listar(
            "activities",
            repo.filtro("activities")
            .igual("related_type", entity_type, ignorar_vazio=False)
            .igual("related_id", entity_id, ignorar_vazio=False),
            limite=100,
        ),
        repo.listar(
            "audit_logs",
            repo.filtro("audit_logs").igual("entity_id", entity_id, ignorar_vazio=False),
            limite=50,
        ),
    )

    eventos = [
        {"at": a["created_at"], "origem": "atividade", "tipo": a.get("type"),
         "titulo": a.get("title"), "detalhe": a.get("description", ""),
         "autor": a.get("owner_name"), "done": a.get("done"), "id": a["id"]}
        for a in atividades
    ] + [
        {"at": l["created_at"], "origem": "sistema", "tipo": l.get("action"),
         "titulo": f"{l.get('action')} {l.get('entity')}", "detalhe": l.get("changes", {}),
         "autor": l.get("actor_name"), "done": True, "id": l["id"]}
        for l in logs
    ]
    eventos.sort(key=lambda e: e["at"], reverse=True)
    return {"eventos": eventos[:120]}


@router.get("/audit")
async def audit_log(
    entity: str = "todos",
    actor_id: str = "",
    page: int = 1,
    page_size: int = 50,
    admin: dict = Depends(require_admin),
):
    f = repo.filtro("audit_logs")
    if entity != "todos":
        f.igual("entity", entity)
    f.igual("actor_id", actor_id)
    return await repo.paginar("audit_logs", f, page=page, page_size=page_size)
