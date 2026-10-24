"""Texto do relatório mostrado no terminal."""
import numpy as np

from .espectro import NOMINAIS
from .solver_eq import PERFIS, Banda, SugestaoEQ

ESCALA_DB = 10  # o gráfico vai de -10 a +10 dB (1 caractere por dB)


def _fmt_freq(hz: float) -> str:
    return f"{hz / 1000:.3g} kHz" if hz >= 1000 else f"{hz:.0f} Hz"


def _fmt_banda(b: Banda) -> str:
    return f"{_fmt_freq(b.freq):>8}  {b.ganho_db:+5.1f} dB  Q {b.q:.1f}"


def _barra(db: float) -> str:
    n = int(round(np.clip(db, -ESCALA_DB, ESCALA_DB)))
    esquerda = " " * (ESCALA_DB - max(0, -n)) + "#" * max(0, -n)
    direita = "#" * max(0, n) + " " * (ESCALA_DB - max(0, n))
    return f"{esquerda}|{direita}"


def grafico(sugestao: SugestaoEQ) -> str:
    linhas = [
        "  Comparação com o alvo (falta <- | -> sobra), em dB:",
        f"  {'Freq':>8}  {'antes':>6}  {'depois':>6}   {'-10':<10}0{'+10':>10}",
    ]
    for i, nominal in enumerate(NOMINAIS):
        if not sugestao.validos[i]:
            continue
        antes, depois = sugestao.desvio[i], sugestao.depois[i]
        linhas.append(f"  {_fmt_freq(nominal):>8}  {antes:+6.1f}  {depois:+6.1f}   {_barra(antes)}")
    return "\n".join(linhas)


def relatorio(sugestao: SugestaoEQ, antes: tuple[float | None, list[Banda]] | None = None) -> str:
    linhas = [f"Perfil: {sugestao.perfil} ({PERFIS[sugestao.perfil]['descricao']})"]
    if sugestao.f0_mediana:
        linhas.append(f"Tom de voz (fundamental média): {sugestao.f0_mediana:.0f} Hz")
    linhas += ["", grafico(sugestao), "", "EQ sugerido:"]

    hpf_antes = f"   (antes: {_fmt_freq(antes[0])})" if antes and antes[0] is not None else ""
    linhas.append(f"  HPF (corta-graves): {_fmt_freq(sugestao.hpf_hz)}{hpf_antes}")
    bandas_antes = antes[1] if antes else []
    for k in range(4):
        if k < len(sugestao.bandas):
            b = sugestao.bandas[k]
            texto = f"{_fmt_banda(b)}   {b.rotulo}"
        else:
            texto = f"{'--':>8}   0.0 dB          (não usada)"
        if k < len(bandas_antes):
            texto += f"   [antes: {_fmt_banda(bandas_antes[k]).strip()}]"
        linhas.append(f"  Banda {k + 1}: {texto}")
    if not sugestao.bandas:
        linhas.append("  A voz já está próxima do alvo; só o HPF foi ajustado.")
    return "\n".join(linhas)
