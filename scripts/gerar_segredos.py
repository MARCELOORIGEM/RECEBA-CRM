"""Gera os segredos da instalação.

    python scripts/gerar_segredos.py > .env

Produz um .env pronto para o docker compose, com senhas aleatórias fortes.
Rode UMA vez por ambiente e guarde o resultado num cofre — rodar de novo gera
segredos diferentes, e trocar o JWT_SECRET derruba todas as sessões abertas.
"""
import secrets
import string
import sys

# O .env tem comentários acentuados. Redirecionando a saída no Windows, o
# Python usaria cp1252 e o arquivo sairia ilegível para o docker compose, que
# lê UTF-8. Forçar aqui é o que faz `gerar_segredos.py > .env` funcionar igual
# nos dois sistemas.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Sem pontuação além de - e _: as senhas do banco entram na URI de conexão
# (postgresql://usuario:senha@db/...), onde @, #, % e / mudam o sentido do
# endereço e a API não conectaria. 28 caracteres deste alfabeto ainda dão
# mais de 160 bits.
ALFABETO = string.ascii_letters + string.digits + "-_"


def senha(tamanho: int = 28) -> str:
    """Senha aleatória sem caracteres que atrapalham em URL de conexão."""
    return "".join(secrets.choice(ALFABETO) for _ in range(tamanho))


def main() -> None:
    dominio = sys.argv[1] if len(sys.argv) > 1 else "https://crm.suaempresa.com.br"
    # O Caddy quer o host puro, sem esquema: é o nome do site no Caddyfile.
    host = dominio.split("://", 1)[-1].rstrip("/")

    print("# Segredos do Miliano CRM — gerados automaticamente.")
    print("# NÃO versione este arquivo. Guarde uma cópia num cofre de senhas.")
    print()
    print("# --- Banco ---")
    print("DB_NAME=miliano_crm")
    print("PG_ROOT_USER=miliano_root")
    print(f"PG_ROOT_PASSWORD={senha()}")
    print("PG_APP_USER=miliano_app")
    print(f"PG_APP_PASSWORD={senha()}")
    print()
    print("# --- Sessão ---")
    print("# Trocar este valor desconecta todo mundo que estiver logado.")
    print(f"JWT_SECRET={secrets.token_hex(48)}")
    print()
    print("# --- Endereços ---")
    print(f"FRONTEND_URL={dominio}")
    print(f"PUBLIC_API_URL={dominio}")
    print()
    print("# --- TLS ---")
    print("# Aponte um A/AAAA deste domínio para o IP do servidor e abra as")
    print("# portas 80 e 443 ANTES de subir: é assim que a Let's Encrypt valida.")
    print(f"DOMINIO={host}")
    print("# Troque pelo e-mail que recebe o aviso de falha na renovação.")
    print("ACME_EMAIL=ti@suaempresa.com.br")
    print()
    print("# HTTP interno, só no loopback — quem atende a internet é o Caddy.")
    print("PORTA_HTTP=8080")
    print("BIND_HTTP=127.0.0.1")
    print()
    print("# --- Contas iniciais ---")
    print("# Troque os e-mails pelos reais ANTES da primeira subida: eles são")
    print("# criados no primeiro boot e a senha daqui só vale nesse momento.")
    print("ADMIN_EMAIL=admin@suaempresa.com.br")
    print(f"ADMIN_PASSWORD={senha(20)}")
    print("MANAGER_EMAIL=gestor@suaempresa.com.br")
    print(f"MANAGER_PASSWORD={senha(20)}")
    print()
    print("# --- Operação ---")
    print("AMBIENTE=producao")
    print("TIMEZONE=America/Sao_Paulo")
    print("SEED_DEMO_DATA=false")
    print("ALLOW_PUBLIC_REGISTER=false")
    print()
    print("# --- Backup ---")
    print("RETENCAO_DIAS=14")
    print("# Cópia para fora da máquina (destino de rclone ou rsync).")
    print("# Backup que mora na mesma VPS não sobrevive à perda dela.")
    print("DESTINO_REMOTO=")
    print()
    print("# --- Alerta de queda ---")
    print("# Webhook (Slack/Discord/Teams) avisado quando a API cai.")
    print("WEBHOOK_ALERTA=")
    print()
    print("# --- Limites de memória ---")
    print("MEM_DB=1g")
    print("MEM_API=1g")
    print("MEM_WEB=256m")
    print("MEM_PROXY=256m")
    print()
    print("# --- Opcionais ---")
    print("# SENTRY_DSN=")
    print("# PRIVACIDADE_URL=https://suaempresa.com.br/privacidade")


if __name__ == "__main__":
    main()
