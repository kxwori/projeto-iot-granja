import json
import tkinter as tk
import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORTA = 1883
TOPICO_COMANDO = "uniso/granja01/atuadores/ventilador/comando"
TOPICO_STATUS = "uniso/granja01/atuadores/ventilador/status"

ligado = False 


def on_connect(client, userdata, flags, rc, props):
    client.subscribe(TOPICO_COMANDO, qos=1)


def on_message(client, userdata, msg):
    global ligado
    texto = msg.payload.decode().strip()
    try:  
        dados = json.loads(texto)
        if isinstance(dados, dict):
            texto = str(dados.get("comando", ""))
    except json.JSONDecodeError:
        pass

    comando = texto.strip('"').upper()
    if comando == "ON":
        ligado = True
        client.publish(TOPICO_STATUS, json.dumps({"status": "rodando"}))
    elif comando == "OFF":
        ligado = False
        client.publish(TOPICO_STATUS, json.dumps({"status": "parado"}))


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect_async(BROKER, PORTA)
client.loop_start()  # roda em segundo plano e reconecta sozinho

# ---------- TELA ----------
janela = tk.Tk()
janela.title("Ventilador")
texto = tk.Label(janela, text="", font=("Arial", 24, "bold"), width=20, height=5)
texto.pack()


def atualizar():
    if ligado:
        texto.config(text="VENTILADOR\nLIGADO", bg="green", fg="white")
    else:
        texto.config(text="VENTILADOR\nDESLIGADO", bg="red", fg="white")
    janela.after(200, atualizar)


atualizar()
janela.mainloop()
