"""EQ automático de voz para a mesa Soundcraft Ui24R.

Exemplos:
  python autoeq.py dispositivos
  python autoeq.py espiar --canal 5
  python autoeq.py calibrar --canal 5 --perfil fala            (só mostra a sugestão)
  python autoeq.py calibrar --canal 5 --perfil fala --aplicar  (aplica na mesa)
  python autoeq.py desfazer --canal 5
"""
import argparse
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from analise import pipeline, relatorio, solver_eq
from ui24r import aplicar, rta
from ui24r.conexao import ErroConexao, Mesa, interpretar_set
from ui24r.mapeamento_eq import interpretar
from ui24r.simulador import MesaSimulada

PASTA = Path(__file__).resolve().parent

PADRAO = {
    "ip_mesa": "10.10.1.1",
    "canal_mesa": 1,
    "perfil": "fala",
    "fonte": "usb",
    "segundos": 15,
    "intensidade": 0.8,
    "audio": {"dispositivo": "Ui24R", "offset_usb": 10, "taxa": 48000, "pos_eq": False},
    "limites": {"ganho_min_db": -8, "ganho_max_db": 4},
}


def carregar_config(caminho: Path) -> dict:
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in PADRAO.items()}
    if caminho.exists():
        lido = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
        for chave, valor in lido.items():
            if isinstance(valor, dict) and isinstance(cfg.get(chave), dict):
                cfg[chave].update(valor)
            else:
                cfg[chave] = valor
    return cfg


def abrir_mesa(args, cfg, base: Path):
    if args.simular:
        print("(modo simulado: nenhuma mesa real será alterada)")
        return MesaSimulada(base / "backups" / "mesa_simulada.json").conectar()
    ip = args.ip or cfg["ip_mesa"]
    print(f"Conectando na mesa em {ip}...")
    mesa = Mesa(ip).conectar()
    if mesa.aguardar_estado() == 0:
        mesa.fechar()
        raise ErroConexao("A mesa conectou mas não enviou o estado. Confira se o IP é mesmo da Ui24R.")
    return mesa


def cmd_dispositivos(args, cfg, base) -> int:
    from audio.captura import listar_dispositivos
    lista = listar_dispositivos()
    if not lista:
        print("Nenhum dispositivo de entrada de áudio encontrado.")
        return 1
    print(f"{'Nº':>3}  {'Entradas':>8}  {'Sistema':<22}  Nome")
    for d in lista:
        print(f"{d['indice']:>3}  {d['entradas']:>8}  {d['hostapi']:<22}  {d['nome']}")
    print("\nUse o número ou parte do nome em 'audio.dispositivo' no config.yaml.")
    return 0


def cmd_espiar(args, cfg, base) -> int:
    pasta = base / "capturas"
    pasta.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    mesa = abrir_mesa(args, cfg, base)
    arquivo_rta = None
    try:
        dump = pasta / f"dump_{carimbo}.txt"
        dump.write_text("\n".join(f"{k}^{v}" for k, v in sorted(mesa.estado.items())), encoding="utf-8")
        print(f"Estado recebido: {len(mesa.estado)} parâmetros (salvo em {dump}).")

        filtro = args.filtro
        if args.canal:
            filtro = f"i.{args.canal - 1}.{args.filtro}" if args.filtro else f"i.{args.canal - 1}."
            print(f"\nEQ atual do canal {args.canal}:")
            for caminho, valor in sorted(mesa.estado.items()):
                if caminho.startswith(f"i.{args.canal - 1}.eq."):
                    desc = interpretar(caminho, valor)
                    print(f"  {caminho} = {valor}" + (f"   -> {desc}" if desc else ""))

        contagem = Counter()
        if args.rta:
            arquivo_rta = (pasta / f"rta_{carimbo}.txt").open("w", encoding="utf-8")
            print(f"Gravando mensagens candidatas a RTA em {arquivo_rta.name}. "
                  "Abra o RTA do canal na interface web e fale no microfone.")

        def ao_receber(msg: str):
            par = interpretar_set(msg)
            if par:
                caminho, valor = par
                if filtro in caminho:
                    desc = interpretar(caminho, valor)
                    print(f"  {caminho} = {valor}" + (f"   -> {desc}" if desc else ""))
            elif arquivo_rta and rta.eh_candidata(msg):
                contagem[msg.split("^", 1)[0][:24]] += 1
                arquivo_rta.write(f"{time.time():.3f}\t{msg}\n")

        mesa.ouvir(ao_receber)
        print(f"\nOuvindo mensagens com '{filtro}' (mexa no EQ pela interface web). Ctrl+C para parar.")
        inicio = time.monotonic()
        ultimo_resumo = inicio
        try:
            while args.segundos is None or time.monotonic() - inicio < args.segundos:
                time.sleep(0.2)
                if args.rta and time.monotonic() - ultimo_resumo >= 5:
                    ultimo_resumo = time.monotonic()
                    print("  [mensagens não-SETD] " + (", ".join(f"{p}: {n}" for p, n in contagem.most_common(8)) or "nenhuma"))
        except KeyboardInterrupt:
            pass
    finally:
        if arquivo_rta:
            arquivo_rta.close()
        mesa.fechar()
    print("Fim.")
    return 0


def obter_sinal(args, cfg, fonte: str, canal: int):
    """Devolve (sinal, taxa) da fonte escolhida."""
    if fonte == "usb":
        from audio.captura import gravar
        canal_usb = canal + int(cfg["audio"]["offset_usb"])
        segundos = args.segundos or cfg["segundos"]
        print(f"\nGravação de {segundos} s: fale/cante como no evento, na distância normal do microfone.")
        sinal, taxa = gravar(cfg["audio"]["dispositivo"], canal_usb, segundos, int(cfg["audio"]["taxa"]))
    elif fonte == "arquivo":
        from audio.arquivo import ler_wav
        if not args.wav:
            raise ValueError("Com --fonte arquivo é preciso informar --wav CAMINHO.wav")
        sinal, taxa = ler_wav(args.wav, args.canal_wav)
        print(f"\nArquivo: {args.wav} ({len(sinal) / taxa:.1f} s, {taxa} Hz)")
    else:
        raise ValueError(f"Fonte desconhecida: {fonte}")
    return sinal, taxa


def cmd_calibrar(args, cfg, base) -> int:
    canal = args.canal or int(cfg["canal_mesa"])
    perfil = args.perfil or cfg["perfil"]
    fonte = args.fonte or cfg["fonte"]
    intensidade = args.intensidade if args.intensidade is not None else float(cfg["intensidade"])
    print(f"== Calibração do canal {canal} | perfil {perfil} | fonte {fonte} ==")

    precisa_mesa = args.aplicar or args.simular or fonte == "rede"
    mesa = abrir_mesa(args, cfg, base) if precisa_mesa else None
    try:
        if fonte == "rede":
            rta.ler_espectro_rta(mesa, canal, args.segundos or cfg["segundos"])
        sinal, taxa = obter_sinal(args, cfg, fonte, canal)
        valores_antes = aplicar.ler_eq(mesa, canal) if mesa else {}
        antes = aplicar.eq_legivel(valores_antes, canal) if valores_antes else None

        existente = None
        if cfg["audio"].get("pos_eq"):
            if antes is None:
                print("  ATENÇÃO: pos_eq ligado mas o EQ atual não foi lido (rode com a mesa conectada).")
            else:
                existente = antes

        resultado = pipeline.analisar(
            sinal, taxa, perfil, intensidade=intensidade,
            ganho_min=float(cfg["limites"]["ganho_min_db"]),
            ganho_max=float(cfg["limites"]["ganho_max_db"]),
            eq_existente=existente,
        )
        sugestao = resultado.sugestao
        print(f"  Voz detectada: {resultado.segundos_voz:.1f} s")
        for aviso in resultado.avisos:
            print(f"  ATENÇÃO: {aviso}")
        print()
        print(relatorio.relatorio(sugestao, antes))
        print()

        if not args.aplicar:
            print("Isto foi só uma PRÉVIA. Para aplicar na mesa, rode de novo com --aplicar.")
            return 0

        backup = aplicar.aplicar_sugestao(mesa, canal, sugestao, base / "backups")
        print(f"EQ aplicado no canal {canal}. Backup do EQ anterior: {backup.name}")
        print(f"Para voltar ao EQ anterior: python autoeq.py desfazer --canal {canal}"
              + (" --simular" if args.simular else ""))
        return 0
    finally:
        if mesa:
            mesa.fechar()


def cmd_desfazer(args, cfg, base) -> int:
    canal = args.canal or int(cfg["canal_mesa"])
    if not aplicar.ultimo_backup(base / "backups", canal):
        print(f"Nenhum backup encontrado para o canal {canal}.")
        return 1
    mesa = abrir_mesa(args, cfg, base)
    try:
        arquivo = aplicar.restaurar_ultimo(mesa, canal, base / "backups")
    finally:
        mesa.fechar()
    print(f"EQ do canal {canal} restaurado a partir de {arquivo.name}.")
    return 0


def criar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="EQ automático de voz para a Soundcraft Ui24R.")
    p.add_argument("--config", type=Path, default=PASTA / "config.yaml", help="arquivo de configuração")
    p.add_argument("--ip", help="IP da mesa (sobrescreve o config)")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("dispositivos", help="lista as entradas de áudio do PC")

    e = sub.add_parser("espiar", help="mostra as mensagens da mesa (confirmar EQ e capturar RTA)")
    e.add_argument("--canal", type=int, help="mostra só este canal")
    e.add_argument("--filtro", default="eq", help="trecho do caminho a mostrar (padrão: eq)")
    e.add_argument("--rta", action="store_true", help="grava mensagens candidatas a RTA em capturas/")
    e.add_argument("--segundos", type=float, help="para sozinho depois de N segundos")
    e.add_argument("--simular", action="store_true", help=argparse.SUPPRESS)

    c = sub.add_parser("calibrar", help="analisa a voz e sugere/aplica o EQ")
    c.add_argument("--canal", type=int, help="entrada da mesa onde está o microfone")
    c.add_argument("--perfil", choices=list(solver_eq.PERFIS), help="fala ou canto")
    c.add_argument("--fonte", choices=["usb", "rede", "arquivo"], help="de onde vem o som analisado")
    c.add_argument("--wav", help="arquivo WAV (com --fonte arquivo)")
    c.add_argument("--canal-wav", type=int, default=1, help="canal dentro do WAV (padrão 1)")
    c.add_argument("--segundos", type=float, help="tempo de gravação")
    c.add_argument("--intensidade", type=float, help="0.5 (suave) a 1.0 (correção total)")
    c.add_argument("--aplicar", action="store_true", help="aplica o EQ na mesa (sem isso é só prévia)")
    c.add_argument("--simular", action="store_true", help="usa uma mesa falsa (testar sem rede)")

    d = sub.add_parser("desfazer", help="volta o EQ do canal para o último backup")
    d.add_argument("--canal", type=int)
    d.add_argument("--simular", action="store_true", help="usa a mesa falsa")
    return p


COMANDOS = {"dispositivos": cmd_dispositivos, "espiar": cmd_espiar,
            "calibrar": cmd_calibrar, "desfazer": cmd_desfazer}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = criar_parser().parse_args(argv)
    if not hasattr(args, "simular"):
        args.simular = False
    cfg = carregar_config(args.config)
    base = args.config.resolve().parent
    try:
        return COMANDOS[args.comando](args, cfg, base)
    except ErroConexao as e:
        print(f"ERRO de conexão: {e}\nConfira se o PC está na rede/Wi-Fi da mesa e se o IP está certo "
              "(config.yaml ou --ip).")
    except rta.RtaIndisponivel as e:
        print(f"ERRO: {e}")
    except Exception as e:  # mensagens amigáveis para erros de áudio/arquivo
        nome = type(e).__name__
        if nome in ("ErroAudio", "ValueError", "FileNotFoundError"):
            print(f"ERRO: {e}")
        else:
            raise
    return 2


if __name__ == "__main__":
    sys.exit(main())
