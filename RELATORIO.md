# Mini-relatório de decisões técnicas — Cérebro (Aluno 3)

**Grupo:**
- Gustavo Henrique Silva - RA: 00123487
- Julia Mayumi Hayashi - RA: 00123374
- Eduardo Augusto - RA: 00124146

## Tópicos MQTT usados

Broker: `broker.emqx.io`, porta `1883`.

| Papel do cérebro | Tópico |
|---|---|
| Assina (sensor) | `uniso/granja01/sensores/temperatura` |
| Publica (comando) | `uniso/granja01/atuadores/ventilador/comando` |
| Assina (feedback, só log) | `uniso/granja01/atuadores/ventilador/status` |

Payload do sensor: `{"temperatura": 32.5, "unidade": "C"}`. Payload do comando: texto `ON` ou `OFF`.

## Regra de negócio

Se a temperatura passar de 30 °C, o cérebro publica `ON`. Se cair abaixo de 26 °C, publica `OFF`. Entre 26 °C e 30 °C ele mantém o estado atual (histerese), para o ventilador não ficar ligando e desligando a cada oscilação.

**Prevenção de spam:** o cérebro guarda o último comando enviado e só publica quando o estado muda. Com a temperatura em 31, 32, 33 °C seguidos, sai um único `ON`. Se o cérebro reiniciar, o estado volta a "desconhecido" e a primeira leitura fora da faixa intermediária reenvia o comando certo, ressincronizando o ventilador.

## Nível de QoS escolhido

**Comando do cérebro para o ventilador: QoS 1, com retain.**
- QoS 0 foi descartado porque perder o comando `ON` em um pico de calor pode custar a vida das aves.
- QoS 2 foi descartado porque `ON` e `OFF` são comandos de estado: receber o mesmo comando duas vezes (possível no QoS 1) não causa problema mecânico nem lógico, o ventilador continua ligado. Pagar o handshake de 4 vias e a latência extra do QoS 2 não traz ganho aqui.
- QoS 2 só passaria a ser obrigatório em comandos que não podem se repetir, como liberar uma dose exata de antibiótico.
- `retain=True` faz o broker guardar o último comando. Se o ventilador cair e reconectar, ele recebe o estado correto na hora.

**Sensor (Aluno 1):** O sensor usa QoS 0. Ele publica uma leitura a cada 5 segundos, então se uma se perder a seguinte chega em 5 segundos e o cérebro decide com ela.

**Ventilador (Aluno 2):** O ventilador assina o comando com QoS 1. O QoS efetivo é o menor entre publicação e assinatura, então com QoS 0 na assinatura o comando do cérebro (QoS 1) poderia se perder. O status é publicado no QoS padrão do paho (0).

## Outras decisões

- `client_id` único (com sufixo aleatório), porque o broker é público e dois clientes com o mesmo id derrubam um ao outro.
- A assinatura é feita dentro do `on_connect`, então ela se refaz sozinha após quedas de conexão.
- Mensagens inválidas (JSON quebrado, texto, temperatura absurda, unidade diferente de °C) são descartadas com aviso no log e não derrubam o serviço.
- O cérebro também aceita um número puro como leitura (ex.: `31.5`), caso o sensor não envie JSON.
- A lógica de decisão fica separada do MQTT, o que permite testá-la sem broker.

## Provas visuais (prints)

1. **Cenário de risco:** terminal do sensor enviando 31 °C.
2. **A decisão:** terminal do cérebro com `Temperatura recebida: 31.0 °C` seguido de `Comando publicado em ...: ON`.
3. **A salvação:** terminal do ventilador recebendo `ON` e mostrando status "Ligado/Rodando".
