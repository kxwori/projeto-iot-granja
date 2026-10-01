"""Cérebro da granja: escuta a temperatura, decide e manda ON/OFF para o ventilador."""
from __future__ import annotations

import json
import paho.mqtt.client as mqtt
from dataclasses import dataclass
from enum import Enum

BROKER = "broker.emqx.io"
PORTA = 1883
TOPICO_SENSOR = "uniso/granja01/sensores/temperatura"
TOPICO_VENTILADOR = "uniso/granja01/ventilador/comando"


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


decider = FanDecider(Thresholds(turn_on_above=30.0, turn_off_below=25.0))
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def on_connect(cliente, userdata, flags, rc, properties=None):
    print("Conectado ao broker MQTT")
    cliente.subscribe(TOPICO_SENSOR, qos=0)
    print(f"Inscrito em: {TOPICO_SENSOR}")


def on_message(cliente, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        temperatura = float(payload["temperatura"])
    except Exception as exc:
        print(f"Mensagem inválida recebida: {msg.payload!r} -> {exc}")
        return

    print(f"Temperatura recebida: {temperatura}°C")
    novo_estado = decider.decide(temperatura)

    if novo_estado is not None:
        mensagem = novo_estado.value
        cliente.publish(TOPICO_VENTILADOR, mensagem, qos=0)
        print(f"Comando enviado para ventilador: {mensagem}")


client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORTA)
client.loop_forever()
