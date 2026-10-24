"""Gravação de um canal de entrada usando a Ui24R como placa de som USB."""
import os
import time

# Liga o suporte a ASIO do sounddevice no Windows (precisa vir antes do import).
os.environ.setdefault("SD_ENABLE_ASIO", "1")

import numpy as np

PREFERENCIA_HOSTAPI = ("ASIO", "WASAPI", "WDM-KS", "MME")


class ErroAudio(Exception):
    pass


def _sd():
    import sounddevice as sd
    return sd


def listar_dispositivos() -> list[dict]:
    sd = _sd()
    hostapis = sd.query_hostapis()
    lista = []
    for idx, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            lista.append({
                "indice": idx,
                "nome": d["name"],
                "hostapi": hostapis[d["hostapi"]]["name"],
                "entradas": d["max_input_channels"],
                "taxa": d["default_samplerate"],
            })
    return lista


def _prioridade(hostapi: str) -> int:
    for i, nome in enumerate(PREFERENCIA_HOSTAPI):
        if nome in hostapi:
            return i
    return len(PREFERENCIA_HOSTAPI)


def encontrar_dispositivo(alvo: str | int) -> dict:
    lista = listar_dispositivos()
    if isinstance(alvo, int) or str(alvo).isdigit():
        for d in lista:
            if d["indice"] == int(alvo):
                return d
        raise ErroAudio(f"Dispositivo de entrada nº {alvo} não existe. Rode: python autoeq.py dispositivos")
    achados = [d for d in lista if str(alvo).lower() in d["nome"].lower()]
    if not achados:
        raise ErroAudio(
            f"Não achei dispositivo de áudio com '{alvo}' no nome. Confira o cabo USB e o driver "
            "da Soundcraft e rode: python autoeq.py dispositivos"
        )
    return min(achados, key=lambda d: (_prioridade(d["hostapi"]), -d["entradas"]))


def configurar_canal(hostapi: str, canal: int, entradas: int, nome: str) -> tuple[int, int, dict]:
    """Como abrir o dispositivo para ler só o `canal` (começa em 1).

    Devolve (nº de canais a abrir, coluna do canal nos dados, argumentos extras do sounddevice).
    """
    if not 1 <= canal <= entradas:
        raise ErroAudio(
            f"O dispositivo '{nome}' tem {entradas} entradas, mas foi pedido o canal {canal}. "
            "Confira canal_mesa e offset_usb no config.yaml."
        )
    if "ASIO" in hostapi:
        return 1, 0, {"extra_settings": _sd().AsioSettings(channel_selectors=[canal - 1])}
    # O WASAPI pode recusar abrir menos canais que o dispositivo tem; por isso abre pelo menos 2.
    return max(canal, min(entradas, 2)), canal - 1, {}


def gravar(dispositivo: str | int, canal_usb: int, segundos: float, taxa: int = 48000) -> tuple[np.ndarray, int]:
    """Grava `segundos` do canal USB `canal_usb` (começa em 1) e devolve (sinal mono, taxa)."""
    sd = _sd()
    info = encontrar_dispositivo(dispositivo)
    canais, coluna, extra = configurar_canal(info["hostapi"], canal_usb, info["entradas"], info["nome"])

    print(f"  Gravando de: {info['nome']} ({info['hostapi']}), canal USB {canal_usb}")
    try:
        dados = sd.rec(int(segundos * taxa), samplerate=taxa, channels=canais,
                       device=info["indice"], dtype="float32", **extra)
        for restante in range(int(round(segundos)), 0, -1):
            print(f"\r  >>> Fale/cante agora... {restante:2d} s ", end="", flush=True)
            time.sleep(1)
        sd.wait()
    except sd.PortAudioError as e:
        raise ErroAudio(f"Erro ao gravar: {e}") from e
    print("\r  Gravação concluída.            ")
    return dados[:, coluna].astype(np.float64), taxa
