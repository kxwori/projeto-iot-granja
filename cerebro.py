from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from enum import Enum

import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORTA = 1883
TOPICO_SENSOR = "uniso/granja01/sensores/temperatura"
TOPICO_VENTILADOR = "uniso/granja01/atuadores/ventilador/comando"
TOPICO_STATUS = "uniso/granja01/atuadores/ventilador/status"

QOS_SENSOR = 1
QOS_COMANDO = 1

LIGAR_ACIMA_DE = 30.0
DESLIGAR_ABAIXO_DE = 26.0

TEMP_MIN_PLAUSIVEL = -50.0
TEMP_MAX_PLAUSIVEL = 150.0

log = logging.getLogger("cerebro")


class FanState(str, Enum):
    ON = "ON"
    OFF = "OFF"


@dataclass(frozen=True)
class Thresholds:
    turn_on_above: float
    turn_off_below: float

    def __post_init__(self) -> None:
        if self.turn_off_below >= self.turn_on_above:
            raise ValueError("turn_off_below deve ser menor que turn_on_above")


class FanDecider:
    """Decide o estado do ventilador e lembra o último comando enviado.

    O estado começa desconhecido (None): após um reinício do cérebro, a primeira
    leitura fora da faixa intermediária sempre gera um comando e ressincroniza
    o ventilador.
    """

    def __init__(self, thresholds: Thresholds):
        self._thresholds = thresholds
        self._state: FanState | None = None

    @property
    def state(self) -> FanState | None:
        return self._state

    def decide(self, temperature: float) -> FanState | None:
        t = self._thresholds
        if temperature > t.turn_on_above and self._state is not FanState.ON:
            self._state = FanState.ON
            return self._state
        if temperature < t.turn_off_below and self._state is not FanState.OFF:
            self._state = FanState.OFF
            return self._state
        return None


class MensagemInvalida(ValueError):
    """Mensagem do sensor fora do formato esperado."""


def ler_temperatura(payload: bytes) -> float:
    """Aceita {"temperatura": 32.5, "unidade": "C"} ou um número puro (ex.: 32.5)."""
    try:
        dados = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MensagemInvalida("payload não é JSON válido") from exc

    if isinstance(dados, dict):
        unidade = dados.get("unidade", "C")
        if str(unidade).strip().lstrip("°").upper() != "C":
            raise MensagemInvalida(f"unidade não suportada: {unidade!r}")
        valor = dados.get("temperatura")
    else:
        valor = dados

    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise MensagemInvalida("temperatura ausente ou não numérica")
    if not math.isfinite(valor) or not TEMP_MIN_PLAUSIVEL <= valor <= TEMP_MAX_PLAUSIVEL:
        raise MensagemInvalida(f"temperatura implausível: {valor}")
    return float(valor)


def processar_mensagem(decider: FanDecider, payload: bytes) -> FanState | None:
    """Mensagem do sensor entra, retorna o comando a enviar ou None."""
    try:
        temperatura = ler_temperatura(payload)
    except MensagemInvalida as exc:
        log.warning("Mensagem do sensor descartada: %s (payload=%r)", exc, payload[:80])
        return None

    log.info("Temperatura recebida: %.1f °C", temperatura)
    novo_estado = decider.decide(temperatura)
    if novo_estado is None:
        log.info("Sem mudança de estado: nenhum comando enviado")
    return novo_estado


def criar_cliente(decider: FanDecider) -> mqtt.Client:
    # Broker público: client_id repetido derruba a conexão de quem já estava lá.
    client_id = f"cerebro-granja01-{uuid.uuid4().hex[:8]}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

    def on_connect(cliente, userdata, flags, reason_code, properties=None):
        if reason_code.is_failure:
            log.error("Falha ao conectar no broker: %s", reason_code)
            return
        log.info("Conectado ao broker MQTT")
        cliente.subscribe(TOPICO_SENSOR, qos=QOS_SENSOR)
        cliente.subscribe(TOPICO_STATUS, qos=0)
        log.info("Inscrito em: %s", TOPICO_SENSOR)
        log.info("Inscrito em: %s (feedback do ventilador)", TOPICO_STATUS)

    def on_message(cliente, userdata, msg):
        if msg.topic == TOPICO_STATUS:
            log.info("Feedback do ventilador: %s", msg.payload.decode("utf-8", errors="replace"))
            return

        novo_estado = processar_mensagem(decider, msg.payload)
        if novo_estado is not None:
            comando = novo_estado.value
            cliente.publish(TOPICO_VENTILADOR, comando, qos=QOS_COMANDO, retain=True)
            log.info("Comando publicado em %s: %s", TOPICO_VENTILADOR, comando)

    client.on_connect = on_connect
    client.on_message = on_message
    return client


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    decider = FanDecider(Thresholds(turn_on_above=LIGAR_ACIMA_DE, turn_off_below=DESLIGAR_ABAIXO_DE))
    client = criar_cliente(decider)
    client.connect(BROKER, PORTA)
    client.loop_forever()


if __name__ == "__main__":
    main()
