"""Leitura do RTA (analisador de espectro) da Ui24R pela rede — AINDA NÃO IMPLEMENTADO.

O formato das mensagens do RTA não é documentado. Para implementar:
1. Na rede da mesa, abra a interface web, vá no EQ do canal do microfone e ligue o RTA.
2. Rode `python autoeq.py espiar --rta --segundos 30` e fale no microfone.
   As mensagens que não são SETD/SETS ficam gravadas em capturas/rta_*.txt.
3. Se nada novo aparecer (a mesa pode mandar o RTA só para quem pediu), grave pelo navegador:
   F12 > Rede (Network) > WS > clique na conexão > Mensagens, e salve/copie as mensagens.
4. Com essas capturas, escrever `ler_espectro_rta` abaixo: decodificar as mensagens em níveis
   por banda e converter para as bandas de 1/3 de oitava de `analise.espectro.CENTROS`.
"""

PREFIXOS_CONHECIDOS = ("SETD", "SETS", "ALIVE")


class RtaIndisponivel(Exception):
    pass


def eh_candidata(msg: str) -> bool:
    """Mensagens que podem conter dados de RTA (tudo que não é comando/estado conhecido)."""
    return msg.split("^", 1)[0] not in PREFIXOS_CONHECIDOS


def ler_espectro_rta(mesa, canal: int, segundos: float):
    raise RtaIndisponivel(
        "A leitura do RTA pela rede ainda não foi implementada: o formato das mensagens precisa "
        "ser capturado na mesa primeiro.\n"
        "  1) Conecte-se à rede da mesa e abra o RTA do canal na interface web.\n"
        "  2) Rode: python autoeq.py espiar --rta --segundos 30   (fale no microfone)\n"
        "  3) Envie o arquivo gerado em capturas/ para implementarmos a decodificação.\n"
        "Enquanto isso, use --fonte usb (cabo USB) ou --fonte arquivo (gravação WAV)."
    )
