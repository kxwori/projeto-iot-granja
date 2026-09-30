import paho.mqtt.client as mqtt
import json
import random
import time


# Configurações do Broker MQTT
BROKER = "broker.emqx.io"
PORTA = 1883
TOPICO = "uniso/granja01/sensores/temperatura"

# Criação do cliente MQTT
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


# Simula a leitura do sensor DHT22
def ler_sensor():
    temperatura = round(random.uniform(20, 40), 1)
    return temperatura


# Cria o payload no formato JSON
def criar_payload(temperatura):
    dados = {
        "temperatura": temperatura,
        "unidade": "C"
    }

    return json.dumps(dados)


# Conecta ao Broker MQTT
client.connect(BROKER, PORTA)

# Mantém a comunicação MQTT ativa
client.loop_start()


# Publicação contínua da temperatura
while True:
    temperatura = ler_sensor()
    payload = criar_payload(temperatura)

    # Publica a temperatura utilizando QoS 0
    client.publish(TOPICO, payload, qos=0)

    print(f"Temperatura publicada: {payload}")

    # Aguarda 5 segundos para realizar uma nova leitura
    time.sleep(5)