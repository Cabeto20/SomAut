"""Leitura do EQ atual, backup, envio do EQ sugerido (com rampa) e restauração."""
import json
import time
from datetime import datetime
from pathlib import Path

from analise.solver_eq import Banda, SugestaoEQ
from . import mapeamento_eq as m


def ler_eq(mesa, canal: int) -> dict[str, float]:
    """Valores 0..1 atuais do EQ do canal (só os que a mesa informou)."""
    valores = {}
    for caminho in m.caminhos_eq(canal):
        texto = mesa.obter(caminho)
        if texto is not None:
            try:
                valores[caminho] = float(texto)
            except ValueError:
                pass
    return valores


def eq_legivel(valores: dict[str, float], canal: int) -> tuple[float | None, list[Banda]]:
    """Converte valores 0..1 em (HPF em Hz, bandas). Bandas incompletas ficam de fora."""
    hpf = valores.get(m.caminho_hpf(canal))
    bandas = []
    for k in range(1, m.NUM_BANDAS + 1):
        freq, ganho, q = (valores.get(m.caminho_banda(canal, k, p)) for p in m.PARAMS_BANDA)
        if None not in (freq, ganho, q):
            bandas.append(Banda(m.valor_para_freq(freq), m.valor_para_ganho(ganho), m.valor_para_q(q)))
    return (m.valor_para_hpf(hpf) if hpf is not None else None), bandas


def alvo_da_sugestao(canal: int, sugestao: SugestaoEQ) -> dict[str, float]:
    """Valores 0..1 a enviar. Bandas não usadas vão para 0 dB (freq/Q ficam como estão)."""
    alvo = {m.caminho_hpf(canal): m.hpf_para_valor(sugestao.hpf_hz)}
    for k in range(1, m.NUM_BANDAS + 1):
        if k <= len(sugestao.bandas):
            b = sugestao.bandas[k - 1]
            alvo[m.caminho_banda(canal, k, "freq")] = m.freq_para_valor(b.freq)
            alvo[m.caminho_banda(canal, k, "q")] = m.q_para_valor(b.q)
            alvo[m.caminho_banda(canal, k, "gain")] = m.ganho_para_valor(b.ganho_db)
        else:
            alvo[m.caminho_banda(canal, k, "gain")] = m.ganho_para_valor(0.0)
    return alvo


def enviar_com_rampa(mesa, alvo: dict[str, float], atual: dict[str, float],
                     duracao: float = 0.5, passos: int = 10):
    """Muda os valores aos poucos para evitar estalos no som."""
    for passo in range(1, passos + 1):
        t = passo / passos
        for caminho, destino in alvo.items():
            origem = atual.get(caminho)
            if origem is None:
                if passo == passos:
                    mesa.setd(caminho, destino)
            else:
                mesa.setd(caminho, origem + (destino - origem) * t)
        if passo < passos:
            time.sleep(duracao / passos)


def salvar_backup(pasta: Path, canal: int, valores: dict[str, float]) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    arquivo = pasta / f"canal_{canal:02d}_{carimbo}.json"
    arquivo.write_text(json.dumps({"canal": canal, "valores": valores}, indent=1), encoding="utf-8")
    return arquivo


def ultimo_backup(pasta: Path, canal: int) -> Path | None:
    arquivos = sorted(pasta.glob(f"canal_{canal:02d}_*.json"))
    return arquivos[-1] if arquivos else None


def carregar_backup(arquivo: Path) -> dict[str, float]:
    return json.loads(arquivo.read_text(encoding="utf-8"))["valores"]


def aplicar_sugestao(mesa, canal: int, sugestao: SugestaoEQ, pasta_backups: Path) -> Path:
    """Guarda o EQ atual em backup e envia o sugerido. Devolve o arquivo de backup."""
    atual = ler_eq(mesa, canal)
    backup = salvar_backup(pasta_backups, canal, atual)
    enviar_com_rampa(mesa, alvo_da_sugestao(canal, sugestao), atual)
    return backup


def restaurar_ultimo(mesa, canal: int, pasta_backups: Path) -> Path | None:
    arquivo = ultimo_backup(pasta_backups, canal)
    if arquivo:
        enviar_com_rampa(mesa, carregar_backup(arquivo), ler_eq(mesa, canal))
    return arquivo
