# EQ automático de voz — Soundcraft Ui24R

O script escuta alguns segundos de voz no microfone, compara com uma curva de referência
(**fala** ou **canto**) e sugere o EQ do canal: o corta-graves (HPF) e até 4 bandas.
Ele só mexe na mesa quando você pede (`--aplicar`), e sempre guarda um backup para desfazer.

Ele nunca mexe em fader, GAIN ou mute, só no EQ do canal escolhido.

## Como as coisas se ligam

```
Microfone ──> medusa ──> entrada N da Ui24R ──USB (som)──> PC ──Wi-Fi/rede (comandos)──> Ui24R
```

- **Rede/Wi-Fi**: o script manda os comandos de EQ para a mesa, igual ao tablet/celular.
- **Som para análise**: o script precisa ouvir a voz. Há três opções (`--fonte`):
  - `usb`: cabo USB-B da Ui24R ao PC (a mesa vira placa de som). É a mais precisa.
  - `arquivo`: uma gravação WAV do microfone (ex.: gravação multitrack da mesa no pendrive).
  - `rede`: ler o analisador (RTA) da própria mesa, sem cabo. **Ainda em construção** (veja abaixo).

## Instalação (uma vez)

No PowerShell, dentro desta pasta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para `--fonte usb`, instale também o driver **Soundcraft Multi-USB** (site da Soundcraft/Harman).

Nos exemplos abaixo, `py` = `.\.venv\Scripts\python.exe`.

## Interface de testes (no navegador)

Dê dois cliques em **`Abrir interface de teste.bat`** (ou rode `py interface.py`). A página abre
no navegador e permite:

1. gravar a voz por qualquer microfone do PC (ex.: o do fone), com medidor de nível;
2. ver o gráfico da voz comparada com o alvo e o EQ sugerido (perfil e intensidade ajustáveis);
3. **ouvir no fone a gravação original e com o EQ**, no mesmo volume, para comparar;
4. salvar a gravação em WAV e aplicar/desfazer na mesa simulada ou na Ui24R real.

Para fechar, feche a janela preta (ou Ctrl+C nela).

A interface dá o mesmo resultado do terminal. Ela usa a mesma análise e as mesmas regras do
`config.yaml`, relido a cada uso. Ao escolher a Ui24R como microfone, o campo **Canal** vira sozinho
"entrada da mesa + offset_usb" (ex.: entrada 1 = canal USB 11). O botão **Ler EQ atual** mostra o EQ
que está na mesa ao lado da sugestão e, com `pos_eq: true`, faz o script descontar esse EQ.

## Configuração

Edite o [config.yaml](config.yaml): IP da mesa, número da entrada do microfone (`canal_mesa`),
perfil e fonte. Qualquer item também pode ser passado na linha de comando.

## Uso

1. **Na primeira vez com a mesa: confirmar o protocolo do EQ.**
   ```
   py autoeq.py espiar --canal 5
   ```
   Abra a interface web da mesa e mexa no EQ do canal 5. O script mostra cada mudança e como
   ele a entendeu (ex.: `banda 2 gain = +6.0 dB`). Se o valor não bater com o da tela, ajuste
   as faixas em [ui24r/mapeamento_eq.py](ui24r/mapeamento_eq.py).

2. **Ver a sugestão (não altera nada):**
   ```
   py autoeq.py calibrar --canal 5 --perfil fala
   ```
   Fale ou cante normalmente, na distância de sempre do microfone, durante a gravação (15 s).
   Antes, ajuste o GAIN para o sinal ficar forte sem estourar (o script avisa se estourar).

3. **Aplicar na mesa:**
   ```
   py autoeq.py calibrar --canal 5 --perfil fala --aplicar
   ```

4. **Não gostou? Desfazer:**
   ```
   py autoeq.py desfazer --canal 5
   ```

Outras opções úteis: `--intensidade 0.5` (correção mais suave), `--perfil canto`,
`--fonte arquivo --wav gravacao.wav`, `--simular` (usa uma mesa falsa para treinar sem a rede).
Veja todas com `py autoeq.py calibrar --help`.

## Como ler o relatório

- O gráfico mostra, por faixa de frequência, quanto a voz está **sobrando (+)** ou **faltando (−)**
  em relação ao alvo, antes e depois do EQ sugerido.
- Cada banda vem com uma explicação: *embolado* (200–600 Hz), *som de caixa/nasal*,
  *presença/inteligibilidade* (2–5 kHz), *sibilância* (o "s" chiado) etc.
- Limites de segurança: no máximo −8 dB de corte e +4 dB de reforço por banda, e nunca reforça
  graves (evita microfonia e som embolado). Os limites ficam no `config.yaml`.

## Pontos ainda a confirmar na mesa real

- **Caminhos e escalas do EQ** (`i.N.eq.b1.gain` etc.): são uma estimativa e devem ser
  confirmados com o passo 1.
- **Canal USB**: por padrão, entrada 1 da mesa = canal USB 11 (`offset_usb: 10`). Se a análise
  pegar o canal errado, ajuste esse número.
- **USB antes ou depois do EQ**: se o áudio que vai pelo USB já passar pelo EQ do canal, coloque
  `pos_eq: true` no config.
- **RTA pela rede** (`--fonte rede`): com o RTA aberto na interface web, rode
  `py autoeq.py espiar --rta --segundos 30` falando no microfone. As mensagens ficam em
  `capturas/`. Com elas dá para decifrar o formato e completar [ui24r/rta.py](ui24r/rta.py).

## Testes

```
py -m pytest
```
