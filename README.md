# EQ automático de voz — Soundcraft Ui24R

O sistema escuta alguns segundos de voz no microfone, compara com uma curva de referência
(**fala** ou **canto**) e sugere o EQ do canal: o corta-graves (HPF) e até 4 bandas.

- Só altera a mesa quando você pede, e antes sempre guarda um backup para **desfazer**.
- Mexe **só no EQ** do canal escolhido. Nunca mexe em fader, GAIN ou mute.
- Pode ser usado de duas formas, com o **mesmo resultado**: pela **interface no navegador** ou pelo
  **terminal**.

## Como as coisas se ligam

```
Microfone ──> medusa ──> entrada N da Ui24R ──USB (som)──> PC ──Wi-Fi/rede (comandos)──> Ui24R
```

- **Rede/Wi-Fi**: o sistema manda os comandos de EQ para a mesa, igual ao tablet/celular.
- **Som para análise**: o sistema precisa ouvir a voz. Há três opções:
  - **USB**: cabo USB-B da Ui24R ao PC (a mesa vira placa de som). É a mais precisa.
  - **Arquivo WAV**: uma gravação do microfone (ex.: gravação multitrack da mesa no pendrive).
  - **Rede (RTA da mesa)**: sem cabo. **Ainda não funciona**; veja [Pendências](#pendências-a-confirmar-na-mesa-real).
- Para testar sem a mesa, dá para usar qualquer microfone do PC (ex.: o do fone) e uma
  **mesa simulada**, que só existe no computador.

## Como a análise funciona

1. Grava uns 15 s de fala ou canto.
2. Separa só os trechos com voz e ignora os silêncios.
3. Mede quanto som existe em cada faixa de frequência, dos graves aos agudos.
4. Compara com a curva do perfil:
   - **fala**: menos embolado, mais presença, para a palavra ficar clara;
   - **canto**: som mais cheio e natural.
5. Detecta o tom da voz para escolher o **HPF** (tira ronco, vento e batidas).
6. Escolhe até 4 bandas onde a diferença é maior e explica cada uma (ex.: "embolado – corte").

**Proteções:** no máximo −8 dB de corte e +4 dB de reforço por banda, e nunca reforça graves
(evita microfonia). As mudanças vão para a mesa aos poucos, para não dar estalo.

## Instalação (uma vez)

No PowerShell, dentro desta pasta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para usar a mesa pelo USB, instale também o driver **Soundcraft Multi-USB** (site da Soundcraft/Harman).

Nos exemplos abaixo, `py` = `.\.venv\Scripts\python.exe`.

## Configuração

Tudo fica no [config.yaml](config.yaml):

| Item | O que é |
|---|---|
| `ip_mesa` | IP da Ui24R (`10.10.1.1` é o padrão quando o PC está no Wi-Fi da própria mesa) |
| `canal_mesa` | número da entrada da mesa onde está o microfone (o que chega pela medusa) |
| `perfil` | `fala` ou `canto` |
| `fonte` | `usb`, `arquivo` ou `rede` (usada pelo terminal) |
| `segundos` | tempo de gravação |
| `intensidade` | 0.5 = correção suave … 1.0 = correção total |
| `audio.dispositivo` | parte do nome da placa de som da mesa (padrão `Ui24R`) |
| `audio.offset_usb` | canais USB 1–10 são masters/aux, então entrada 1 da mesa = canal USB 11 |
| `audio.pos_eq` | `true` se o áudio analisado já passa pelo EQ do canal (o sistema desconta o EQ atual) |
| `limites` | maior corte e maior reforço permitidos por banda |

A interface e o terminal releem o arquivo a cada uso; não precisa reiniciar nada.

## Forma 1: interface no navegador

Dê dois cliques em **`Abrir interface de teste.bat`** (ou rode `py interface.py`). A página abre
sozinha no navegador. Para fechar, feche a janela preta.

1. **Gravar a voz**
   - Escolha o **Microfone**. O microfone do fone já vem selecionado, se houver um.
   - **Canal**: com o fone, deixe 1. Ao escolher a **Ui24R**, ele vira sozinho "entrada da mesa + 10".
   - Clique em **● Gravar** e fale ou cante uns 15 s. Mantenha a barra no verde; vermelho = estourou.
   - Ou abra um **WAV** (escolha o *canal do WAV* se o arquivo tiver vários canais).
2. **Analisar**: roda sozinho ao fim da gravação. Trocar o perfil ou a intensidade refaz na hora.
   Aparecem o gráfico "sobrando/faltando", a tabela do EQ sugerido e a curva do EQ.
3. **Ouvir no fone**: **▶ Original** e **▶ Com EQ** tocam no mesmo volume, para comparar de forma
   justa. **Salvar gravação** guarda o WAV em `gravacoes/`.
4. **Mesa (opcional)**: escolha *Mesa simulada* ou *Ui24R real*, o IP e o canal.
   - **Ler EQ atual**: mostra o EQ que está na mesa ao lado da sugestão (tabela e curva tracejada).
     Com `pos_eq: true`, clique nele **antes** de analisar.
   - **Aplicar EQ** / **Desfazer**. Na mesa real, ela pede confirmação antes.

## Forma 2: terminal

1. **Na primeira vez com a mesa, confirme o protocolo do EQ:**
   ```
   py autoeq.py espiar --canal 5
   ```
   Abra a interface web da mesa e mexa no EQ do canal 5. O script mostra cada mudança e como a
   entendeu (ex.: `banda 2 gain = +6.0 dB`). Se não bater com a tela, ajuste
   [ui24r/mapeamento_eq.py](ui24r/mapeamento_eq.py).
2. **Ver a sugestão (não altera nada):**
   ```
   py autoeq.py calibrar --canal 5 --perfil fala
   ```
   Antes, ajuste o GAIN para o sinal ficar forte sem estourar (o script avisa se estourar).
3. **Aplicar na mesa:**
   ```
   py autoeq.py calibrar --canal 5 --perfil fala --aplicar
   ```
4. **Desfazer:**
   ```
   py autoeq.py desfazer --canal 5
   ```

Outros comandos e opções:

| Comando / opção | Para que serve |
|---|---|
| `py autoeq.py dispositivos` | lista as entradas de áudio do PC |
| `--fonte arquivo --wav x.wav --canal-wav 2` | analisa uma gravação (e escolhe o canal dentro dela) |
| `--intensidade 0.5` | correção mais suave |
| `--simular` | usa a mesa simulada (treinar sem a rede) |
| `--ip 192.168.x.x` | outro IP sem mexer no config |
| `espiar --rta --segundos 30` | grava as mensagens da mesa para decifrar o RTA |

Veja todas com `py autoeq.py calibrar --help`.

## Como ler o resultado

- O gráfico mostra, por faixa de frequência, quanto a voz está **sobrando (+)** ou **faltando (−)**
  em relação ao alvo, antes e depois do EQ sugerido.
- Cada banda vem com uma explicação: *embolado* (200–600 Hz), *som de caixa/nasal*,
  *presença/inteligibilidade* (2–5 kHz), *sibilância* (o "s" chiado) etc.
- Teste com o fone: o resultado corrige "sua voz + o microfone do fone". Serve para aprender e
  ouvir o efeito, mas o EQ da mesa precisa vir da análise do **microfone ligado na mesa**.

## Pastas criadas pelo sistema

| Pasta | Conteúdo |
|---|---|
| `backups/` | EQ anterior de cada canal antes de aplicar (usado pelo *Desfazer*) e o estado da mesa simulada |
| `gravacoes/` | gravações salvas pela interface |
| `capturas/` | mensagens da mesa gravadas pelo `espiar` |

## Pendências a confirmar na mesa real

- **Caminhos e escalas do EQ** (`i.N.eq.b1.gain` etc.): são estimativas. Confirme com o `espiar`
  (passo 1 do terminal).
- **Canal USB**: por padrão, entrada 1 da mesa = canal USB 11 (`offset_usb: 10`). Se a análise
  pegar o canal errado, ajuste esse número.
- **USB antes ou depois do EQ**: se o áudio do USB já passar pelo EQ do canal, use `pos_eq: true`.
- **RTA pela rede** (sem cabo): com o RTA aberto na interface web da mesa, rode
  `py autoeq.py espiar --rta --segundos 30` falando no microfone. As mensagens ficam em
  `capturas/`. Com elas dá para completar [ui24r/rta.py](ui24r/rta.py). Se nada aparecer, grave
  pelo navegador: F12 > Rede (Network) > WS > mensagens.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Erro ao gravar com um microfone | Escolha outro na lista (ex.: a webcam pode estar desconectada ou em uso). |
| "tem 2 entradas, mas foi pedido o canal 11" | O canal é maior que o dispositivo. Com fone use canal 1; com a Ui24R confira `canal_mesa` e `offset_usb`. |
| "Sinal fraco" / "Clipping" | Ajuste o GAIN na mesa (ou o volume do microfone no Windows) e grave de novo. |
| "Não consegui conectar" na mesa | Confira se o PC está na rede/Wi-Fi da mesa e o IP. |
| A Ui24R não aparece em *dispositivos* | Confira o cabo USB-B e o driver Soundcraft Multi-USB. |

## Estrutura do código

| Arquivo | Função |
|---|---|
| [autoeq.py](autoeq.py) | comandos do terminal |
| [interface.py](interface.py) + [web/index.html](web/index.html) | interface no navegador |
| [analise/](analise/) | detecção de voz, espectro, tom da voz, cálculo do EQ, relatório |
| [audio/](audio/) | gravação (USB/microfone) e leitura/gravação de WAV |
| [ui24r/](ui24r/) | conexão com a mesa, mapeamento do EQ, mesa simulada, backup/desfazer, RTA |
| [tests/](tests/) | testes automáticos |

## Testes

```
py -m pytest
```
