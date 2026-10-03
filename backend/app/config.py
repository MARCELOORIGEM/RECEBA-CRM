"""Configuração central lida do .env — sem os.environ espalhado pelo código."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    """Inteiro do ambiente, caindo no padrão quando vier vazio ou torto."""
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    def __init__(self) -> None:
        self.mongo_url = os.environ["MONGO_URL"]
        self.db_name = os.environ["DB_NAME"]
        self.jwt_secret = os.environ["JWT_SECRET"]
        self.jwt_algorithm = "HS256"
        self.access_ttl_minutes = int(os.environ.get("ACCESS_TTL_MINUTES", "60"))
        self.refresh_ttl_days = int(os.environ.get("REFRESH_TTL_DAYS", "7"))

        # Fuso do negócio. Define onde começa e termina "hoje" nos painéis e na
        # agenda; em UTC, o dia virava às 21h no horário de São Paulo.
        self.timezone = os.environ.get("TIMEZONE", "America/Sao_Paulo")

        self.frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")

        # Cookies cross-site (SameSite=None) exigem HTTPS. Em dev HTTP isso faz o
        # navegador descartar o cookie silenciosamente: o login "passa" e a sessão
        # nunca gruda. Por isso o padrão acompanha o esquema do frontend.
        https = self.frontend_url.startswith("https://")
        self.cookie_secure = _bool("COOKIE_SECURE", https)
        self.cookie_samesite = os.environ.get("COOKIE_SAMESITE", "none" if https else "lax")

        self.ambiente = os.environ.get("AMBIENTE", "desenvolvimento")

        origins = os.environ.get("CORS_ORIGINS", "")
        parsed = [o.strip() for o in origins.split(",") if o.strip() and o.strip() != "*"]
        permitidas = parsed + [self.frontend_url]
        # `http://localhost:3000` entrava na lista SEMPRE, inclusive em
        # produção: uma origem a mais com allow_credentials que ninguém pediu.
        # Em produção vale só o domínio real (mais o que estiver em
        # CORS_ORIGINS, para quem tem painel em subdomínio separado).
        if self.ambiente != "producao":
            permitidas.append("http://localhost:3000")
        self.cors_origins = list(dict.fromkeys(permitidas))

        self.admin_email = os.environ.get("ADMIN_EMAIL", "").lower()
        self.admin_password = os.environ.get("ADMIN_PASSWORD", "")
        self.manager_email = os.environ.get("MANAGER_EMAIL", "").lower()
        self.manager_password = os.environ.get("MANAGER_PASSWORD", "")

        # Padrão DESLIGADO. Ligado por omissão, uma subida em produção nasce
        # com 6 restaurantes e 24 pedidos fictícios misturados ao dado real.
        self.seed_demo = _bool("SEED_DEMO_DATA", False)

        # Só leia X-Forwarded-For quando houver mesmo um proxy confiável na
        # frente: o cabeçalho é forjável e, sem proxy, viraria uma forma de
        # escapar dos limites por IP.
        self.trusted_proxy = _bool("TRUSTED_PROXY", False)

        # Monitoramento de erro. Vazio = desligado, sem dependência extra.
        self.sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()

        # Quantos envios o mesmo IP pode fazer por hora no formulário
        # público. Vale subir em dia de ação de rua, quando muita gente se
        # cadastra pela mesma rede.
        self.max_envios_por_ip = _int("MAX_ENVIOS_POR_IP", 10)

        # Aviso de privacidade exibido no formulário público (LGPD).
        self.privacidade_url = os.environ.get("PRIVACIDADE_URL", "").strip()
        self.privacidade_texto = os.environ.get(
            "PRIVACIDADE_TEXTO",
            "Seus dados serão usados exclusivamente para cadastro e pagamento "
            "das entregas, e não serão compartilhados com terceiros.",
        ).strip()
        self.allow_public_register = _bool("ALLOW_PUBLIC_REGISTER", False)
        self.login_max_attempts = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "8"))
        self.login_window_minutes = int(os.environ.get("LOGIN_WINDOW_MINUTES", "15"))


settings = Settings()
