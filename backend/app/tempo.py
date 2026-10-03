"""Limites de dia e mês no fuso do negócio.

Os cálculos de "hoje" usavam meia-noite **UTC**. Para uma operação em São Paulo
(UTC-3), a meia-noite UTC cai às 21h do dia anterior: das 21h à meia-noite —
justamente o pico do delivery — as entregas eram contadas no dia seguinte, e uma
tarefa marcada para as 22h aparecia como "amanhã".

Tudo aqui devolve datetime em UTC, que é como as datas são gravadas, mas com a
fronteira do dia calculada no fuso local.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import settings


def _carregar_fuso(nome: str) -> ZoneInfo:
    """Windows não traz base de fusos; o pacote `tzdata` supre isso. Se faltar,
    a API sobe em UTC avisando, em vez de morrer no import."""
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        logging.getLogger("miliano").warning(
            "Fuso '%s' indisponível (instale o pacote tzdata). Usando UTC.", nome
        )
        return ZoneInfo("UTC") if nome != "UTC" else timezone.utc


FUSO = _carregar_fuso(settings.timezone)


def agora_local() -> datetime:
    return datetime.now(FUSO)


def hoje_local() -> date:
    return agora_local().date()


def inicio_do_dia(offset_dias: int = 0) -> datetime:
    """Meia-noite local do dia, convertida para UTC."""
    dia = hoje_local() + timedelta(days=offset_dias)
    return datetime.combine(dia, time.min, tzinfo=FUSO).astimezone(timezone.utc)


def fim_do_dia(offset_dias: int = 0) -> datetime:
    dia = hoje_local() + timedelta(days=offset_dias)
    return datetime.combine(dia, time.max, tzinfo=FUSO).astimezone(timezone.utc)


def inicio_do_mes() -> datetime:
    primeiro = hoje_local().replace(day=1)
    return datetime.combine(primeiro, time.min, tzinfo=FUSO).astimezone(timezone.utc)


def dia_local(offset_dias: int = 0) -> str:
    """Data local no formato ISO, para comparar com campos `due_date`."""
    return (hoje_local() + timedelta(days=offset_dias)).isoformat()


def campo_data(campo: str) -> dict:
    """Converte o campo ISO em texto para data BSON, dentro de uma agregação.

    As datas são gravadas como string ISO; sem esta conversão o Mongo não sabe
    aplicar fuso e o agrupamento por dia/hora sai em UTC.
    """
    return {"$dateFromString": {"dateString": f"${campo}", "onError": None, "onNull": None}}
