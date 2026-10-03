"""Fronteiras de dia no fuso do negócio.

Regressão: os recortes de "hoje" usavam meia-noite UTC. Em São Paulo (UTC-3),
isso faz o dia virar às 21h — no pico do delivery. Pedidos entregues entre 21h e
meia-noite iam para o dia seguinte no painel, e uma tarefa marcada para as 22h
aparecia na aba "Próximas" em vez de "Hoje".
"""
from datetime import timedelta, timezone

import pytest

from app import tempo
from app.config import settings


def test_fuso_configurado():
    assert str(tempo.FUSO) == settings.timezone


def test_inicio_do_dia_e_meia_noite_local():
    inicio = tempo.inicio_do_dia()
    assert inicio.tzinfo is not None, "precisa ser um datetime com fuso"
    local = inicio.astimezone(tempo.FUSO)
    assert (local.hour, local.minute, local.second) == (0, 0, 0)
    assert local.date() == tempo.hoje_local()


def test_fim_do_dia_e_o_ultimo_instante_local():
    local = tempo.fim_do_dia().astimezone(tempo.FUSO)
    assert (local.hour, local.minute) == (23, 59)
    assert local.date() == tempo.hoje_local()


def test_dia_local_dura_24_horas():
    duracao = tempo.inicio_do_dia(1) - tempo.inicio_do_dia()
    assert timedelta(hours=23) <= duracao <= timedelta(hours=25)


def test_limite_difere_da_meia_noite_utc_em_fuso_deslocado():
    """O ponto da correção: com deslocamento, a fronteira local não coincide
    com a meia-noite UTC — era exatamente essa a suposição antiga.

    A virada do dia local, lida em UTC, cai no horário do próprio deslocamento:
    em São Paulo (UTC-3), às 03:00 UTC. Comparar com "meia-noite UTC de hoje"
    não serve, porque depois das 21h locais a data UTC já é a do dia seguinte —
    que é exatamente a situação que motivou a correção.
    """
    offset = tempo.agora_local().utcoffset()
    inicio = tempo.inicio_do_dia()
    assert inicio.tzinfo == timezone.utc or inicio.utcoffset() == timedelta(0)

    if offset != timedelta(0):
        assert (inicio.hour, inicio.minute) != (0, 0), "caiu na meia-noite UTC"
        horas_de_deslocamento = (-offset).total_seconds() / 3600 % 24
        assert inicio.hour + inicio.minute / 60 == pytest.approx(horas_de_deslocamento)


def test_inicio_do_mes_e_o_primeiro_dia_local():
    local = tempo.inicio_do_mes().astimezone(tempo.FUSO)
    assert local.day == 1
    assert (local.hour, local.minute) == (0, 0)
    assert local.month == tempo.hoje_local().month


def test_dia_local_formatado():
    assert tempo.dia_local() == tempo.hoje_local().isoformat()
    assert tempo.dia_local(-1) < tempo.dia_local() < tempo.dia_local(1)
