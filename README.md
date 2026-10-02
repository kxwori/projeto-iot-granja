# Controle de ventilação de granja com MQTT

Sistema de três programas Python que se comunicam por um broker MQTT: um sensor simulado publica a temperatura, um "cérebro" decide se o ventilador deve ligar ou desligar e publica essa decisão, e um ventilador simulado mostra seu estado em uma janela.

> Este README descreve somente o que está nos arquivos do projeto: `sensor.py`, `cerebro.py`, `ventilador.py`, `test_cerebro.py`, `requirements.txt` e `RELATORIO.md`.

## Integrantes

Nomes conforme o `RELATORIO.md`:

- Gustavo Henrique Silva (responsável pelo cérebro, segundo o título do relatório: "Cérebro (Aluno 3)")
- Julia Mayumi Hayashi
- Eduardo Augusto

## Arquivos

| Arquivo | O que faz |
|---|---|
| `sensor.py` | Simula um sensor de temperatura e publica uma leitura a cada 5 segundos |
| `cerebro.py` | Assina a temperatura, aplica a regra de decisão e publica `ON` ou `OFF` |
| `ventilador.py` | Assina o tópico de comando, interpreta `ON`/`OFF`, mostra o estado em uma janela e publica um status |
| `requirements.txt` | Dependência: `paho-mqtt` (sem versão fixada) |
| `RELATORIO.md` | Mini-relatório de decisões técnicas do cérebro |

## Broker e tópicos

Os três programas usam o broker `broker.emqx.io`, porta `1883`.

| Arquivo | Assina | Publica |
|---|---|---|
| `sensor.py` | (nenhum) | `uniso/granja01/sensores/temperatura` (QoS 0) |
| `cerebro.py` | `uniso/granja01/sensores/temperatura` (QoS 1)<br>`uniso/granja01/atuadores/ventilador/status` (QoS 0) | `uniso/granja01/atuadores/ventilador/comando` (QoS 1, `retain=True`) |
| `ventilador.py` | `uniso/granja01/atuadores/ventilador/comando` (QoS 1) | `uniso/granja01/atuadores/ventilador/status` (sem QoS explícito) |

```
sensor.py ──[sensores/temperatura]──▶ cerebro.py ──[atuadores/ventilador/comando]──▶ ventilador.py
                                           ▲                                               │
                                           └────────[atuadores/ventilador/status]──────────┘
```

O QoS efetivo de uma entrega é o menor entre o QoS da publicação e o da assinatura.

## Formato das mensagens

**Leitura do sensor** (JSON, publicada por `sensor.py`):

```json
{"temperatura": 32.5, "unidade": "C"}
```

**Leitura aceita pelo cérebro** (`cerebro.py`):

- o JSON acima, ou um número puro (ex.: `31.5`);
- `unidade` ausente é tratada como Celsius; `C`, `c` e `°C` são aceitas, qualquer outra unidade é rejeitada;
- temperaturas fora do intervalo de -50 a 150, `NaN` e valores não numéricos são rejeitados.

**Comando do cérebro** (texto simples, publicado por `cerebro.py`): `ON` ou `OFF`.

**Comandos aceitos pelo ventilador** (`ventilador.py`): o texto `ON` ou `OFF`, sem diferenciar maiúsculas de minúsculas, com ou sem aspas, ou um objeto JSON com a chave `comando` (ex.: `{"comando": "ON"}`). Qualquer outro conteúdo é ignorado.

**Status do ventilador** (JSON, publicado por `ventilador.py` a cada `ON` ou `OFF` recebido):

| Comando recebido | Status publicado |
|---|---|
| `ON` | `{"status": "rodando"}` |
| `OFF` | `{"status": "parado"}` |

## Como cada componente funciona

### Sensor (`sensor.py`)

- Conecta ao broker e entra em um laço infinito.
- A cada iteração gera uma temperatura aleatória entre 20 e 40, arredondada para uma casa decimal (`random.uniform(20, 40)`). O comentário no código diz que isso simula a leitura de um sensor DHT22.
- Publica o JSON da leitura com **QoS 0**, imprime `Temperatura publicada: {...}` no terminal e espera 5 segundos.

### Cérebro (`cerebro.py`)

Estrutura do arquivo:

| Parte | Função |
|---|---|
| `FanState` | Estados `ON` e `OFF` |
| `Thresholds` | Guarda os dois limites e recusa configuração em que `turn_off_below` seja maior ou igual a `turn_on_above` |
| `FanDecider` | Decide o próximo estado e guarda o último estado enviado |
| `ler_temperatura` | Valida e converte o payload do sensor; levanta `MensagemInvalida` se estiver fora do formato |
| `processar_mensagem` | Payload do sensor entra; sai o comando a enviar ou `None` |
| `criar_cliente` | Monta o cliente MQTT e os callbacks `on_connect` e `on_message` |
| `main` | Configura o log, conecta ao broker e roda `loop_forever()` |


**Regra de decisão** (`LIGAR_ACIMA_DE = 30.0`, `DESLIGAR_ABAIXO_DE = 26.0`):

| Condição | Resultado |
|---|---|
| temperatura **maior que** 30,0 e o último estado não é `ON` | publica `ON` |
| temperatura **menor que** 26,0 e o último estado não é `OFF` | publica `OFF` |
| qualquer outro caso (inclui 26,0 a 30,0 e repetição do mesmo estado) | não publica nada |

O estado inicial do `FanDecider` é desconhecido (`None`). Por isso, depois de um reinício do cérebro, a primeira leitura fora da faixa de 26,0 a 30,0 sempre gera um comando. Exemplo, derivado da lógica do código:

| Leitura (°C) | Comando publicado |
|---|---|
| 24 | `OFF` (estado ainda desconhecido) |
| 28 | nenhum |
| 31 | `ON` |
| 33 | nenhum (já está `ON`) |
| 28 | nenhum |
| 25 | `OFF` |

**MQTT:**

- Usa um `client_id` no formato `cerebro-granja01-` seguido de 8 caracteres hexadecimais aleatórios.
- Assina os tópicos dentro de `on_connect`, então as assinaturas são refeitas a cada conexão.
- Publica o comando com `qos=1` e `retain=True`.
- Mensagens no tópico de status são apenas registradas no log (`Feedback do ventilador: ...`).

**Mensagens inválidas:** se `ler_temperatura` rejeitar o payload, o cérebro registra um aviso (`Mensagem do sensor descartada: ...`), não publica nada e continua rodando.

**Log no terminal** (cada linha começa com data, hora e nível, ex.: `2026-10-02 10:15:03,123 INFO ...`):

```
Conectado ao broker MQTT
Inscrito em: uniso/granja01/sensores/temperatura
Inscrito em: uniso/granja01/atuadores/ventilador/status (feedback do ventilador)
Temperatura recebida: 31.0 °C
Comando publicado em uniso/granja01/atuadores/ventilador/comando: ON
Temperatura recebida: 32.0 °C
Sem mudança de estado: nenhum comando enviado
Feedback do ventilador: {"status": "rodando"}
```

### Ventilador (`ventilador.py`)

- Conecta ao broker de forma assíncrona (`connect_async` + `loop_start`) e assina `uniso/granja01/atuadores/ventilador/comando` com QoS 1, dentro de `on_connect`.
- Mantém uma variável `ligado`, que começa em `False`.
- Mostra uma janela Tkinter intitulada "Ventilador", atualizada a cada 200 ms:
  - ligado: texto `VENTILADOR LIGADO` com fundo verde;
  - desligado: texto `VENTILADOR DESLIGADO` com fundo vermelho.
- Ao receber `ON` ou `OFF`, atualiza `ligado` e publica o status no tópico de status, sem especificar QoS.
- Como o cérebro publica o comando com `retain=True` e o ventilador assina dentro de `on_connect`, um ventilador que (re)conecta recebe o último comando retido pelo broker e o trata como qualquer outro comando.
- Não imprime nada no terminal.

## Dependências e execução

- `requirements.txt` lista apenas `paho-mqtt`, sem versão. Os programas usam `mqtt.CallbackAPIVersion.VERSION2`, recurso da série 2.x do `paho-mqtt`.
- `ventilador.py` usa `tkinter` para a janela.

```bash
pip install -r requirements.txt
```

Cada programa fica em execução contínua (laço infinito, `loop_forever` ou janela), então use um terminal para cada um:

```bash
python cerebro.py
python sensor.py
python ventilador.py   # abre a janela do ventilador
```

```bash
pip install pytest
pytest
```

## Limitações

Verificadas nos arquivos:

- O cérebro só registra o status do ventilador no log; nenhuma decisão depende dele.
- Se não houver comando retido no broker e a primeira leitura do cérebro estiver entre 26,0 e 30,0, nenhum comando é enviado até uma leitura sair dessa faixa, porque o estado inicial é desconhecido.
