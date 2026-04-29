# Briscola - Bot + Online

Questo repository contiene:

```text
client/
  briscola_launcher.py        # menu iniziale: bot oppure online
  briscola_bot.py             # gioco contro il computer
  briscola_online_client.py   # client online
  requirements_client.txt     # dipendenze per giocare sul PC

server_online/
  briscola_online_server.py   # server WebSocket da mettere su Render
  requirements.txt            # dipendenze del server

render.yaml                   # configurazione opzionale Render Blueprint
```

## Cartelle da aggiungere nel client

Nel folder `client/` devi mettere anche le tue cartelle:

```text
client/
  carte/
    retro.png
    coppe_asso.png
    coppe_3.png
    ...
  suoni/
    gioca.wav
    pesca.wav
  icona.png       # opzionale
```

## Avvio locale del client

Da terminale:

```bash
cd client
python -m pip install -r requirements_client.txt
python briscola_launcher.py
```

## Test server locale

In un terminale:

```bash
cd server_online
python -m pip install -r requirements.txt
python briscola_online_server.py
```

Nel client, come Server URL usa:

```text
ws://localhost:8765
```

## Deploy server su Render

1. Carica questa cartella su GitHub.
2. Su Render crea un nuovo Web Service collegato al repository.
3. Se non usi `render.yaml`, imposta:
   - Root Directory: `server_online`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python briscola_online_server.py`
4. Dopo il deploy, Render ti darà un URL tipo:

```text
https://briscola-online-server.onrender.com
```

Nel client usa lo stesso URL ma con `wss://`:

```text
wss://briscola-online-server.onrender.com
```

## Note

- Il server gestisce mazzo, turni, punteggi e stanze.
- Ogni client riceve solo le proprie carte.
- L'avversario vede solo il numero di carte coperte.
