import asyncio
import json
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8765"))

SEMI = ["coppe", "denari", "spade", "bastoni"]

VALORI = [
    ("asso", 11, 10),
    ("3", 10, 9),
    ("re", 4, 8),
    ("cavallo", 3, 7),
    ("fante", 2, 6),
    ("7", 0, 5),
    ("6", 0, 4),
    ("5", 0, 3),
    ("4", 0, 2),
    ("2", 0, 1),
]


def make_card(seme: str, nome: str, punti: int, forza: int) -> dict[str, Any]:
    return {
        "id": f"{seme}_{nome}",
        "seme": seme,
        "nome": nome,
        "punti": punti,
        "forza": forza,
    }


def make_deck() -> list[dict[str, Any]]:
    deck = [make_card(s, n, p, f) for s in SEMI for n, p, f in VALORI]

    for _ in range(5):
        random.shuffle(deck)

    return deck


def winner_of_trick(
    first_seat: str,
    c1: dict[str, Any],
    second_seat: str,
    c2: dict[str, Any],
    briscola: str,
) -> str:
    if c1["seme"] == c2["seme"]:
        return first_seat if c1["forza"] > c2["forza"] else second_seat

    if c2["seme"] == briscola:
        return second_seat

    if c1["seme"] == briscola:
        return first_seat

    return first_seat


@dataclass(eq=False)
class Client:
    websocket: WebSocket
    name: str = "Giocatore"
    room_code: str | None = None
    seat: str | None = None
    alive: bool = True

    async def send(self, obj: dict[str, Any]) -> bool:
        if not self.alive:
            return False

        try:
            await self.websocket.send_text(json.dumps(obj, ensure_ascii=False))
            return True
        except Exception as exc:
            print(f"[send-error] {exc}")
            self.alive = False
            return False


@dataclass
class Room:
    code: str
    players: dict[str, Client] = field(default_factory=dict)
    hands: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: {"p1": [], "p2": []})
    points: dict[str, int] = field(default_factory=lambda: {"p1": 0, "p2": 0})
    tricks: dict[str, int] = field(default_factory=lambda: {"p1": 0, "p2": 0})
    played: dict[str, dict[str, Any] | None] = field(default_factory=lambda: {"p1": None, "p2": None})
    deck: list[dict[str, Any]] = field(default_factory=list)
    briscola_fisica: dict[str, Any] | None = None
    seme_briscola: str | None = None
    turn: str = "p1"
    chi_inizia: str | None = None
    started: bool = False
    resolving: bool = False
    game_over: bool = False
    status: str = "In attesa dell'altro giocatore..."
    animations_enabled: bool = True
    animation_speed: str = "Normale"
    match_target: int = 1
    match_wins: dict[str, int] = field(default_factory=lambda: {"p1": 0, "p2": 0})
    round_number: int = 1
    disconnected: bool = False
    rematch_votes: set[str] = field(default_factory=set)
    last_chat: dict[str, Any] | None = None
    chat_seq: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def other(self, seat: str) -> str:
        return "p2" if seat == "p1" else "p1"

    def start(self) -> None:
        self.match_wins = {"p1": 0, "p2": 0}
        self.round_number = 1
        self.disconnected = False
        self.rematch_votes.clear()
        self.last_chat = None
        self.start_round()

    def start_round(self) -> None:
        self.deck = make_deck()
        self.hands["p1"] = [self.deck.pop(0) for _ in range(3)]
        self.hands["p2"] = [self.deck.pop(0) for _ in range(3)]
        self.points = {"p1": 0, "p2": 0}
        self.tricks = {"p1": 0, "p2": 0}
        self.played = {"p1": None, "p2": None}
        self.briscola_fisica = self.deck.pop()
        self.seme_briscola = self.briscola_fisica["seme"]
        self.turn = "p2"
        self.chi_inizia = None
        self.started = True
        self.game_over = False
        self.resolving = False
        self.disconnected = False
        self.status = f"Partita {self.round_number} del match. Tocca al giocatore 2." if self.match_target > 1 else "Partita iniziata. Tocca al giocatore 2."

    def card_by_id(self, seat: str, card_id: str) -> dict[str, Any] | None:
        for card in self.hands[seat]:
            if card["id"] == card_id:
                return card

        return None

    async def play_card(self, seat: str, card_id: str) -> tuple[bool, str]:
        async with self.lock:
            if not self.started:
                return False, "La partita non è ancora iniziata."

            if self.game_over:
                return False, "La partita è già finita."

            if self.resolving:
                return False, "Attendi la risoluzione della mano."

            if seat != self.turn:
                return False, "Non è il tuo turno."

            if self.played[seat] is not None:
                return False, "Hai già giocato una carta."

            card = self.card_by_id(seat, card_id)

            if card is None:
                return False, "Carta non valida."

            self.hands[seat].remove(card)
            self.played[seat] = card

            other = self.other(seat)

            if self.chi_inizia is None:
                self.chi_inizia = seat

            if self.played[other] is None:
                self.turn = other
                self.status = f"{self.players[seat].name} ha giocato. Tocca a {self.players[other].name}."
                return True, "ok"

            self.resolving = True
            self.status = "Carte giocate: risoluzione della mano..."
            return True, "resolve"

    async def resolve_trick(self) -> None:
        async with self.lock:
            if not self.started or self.game_over:
                return

            if not self.played["p1"] or not self.played["p2"]:
                return

            first = self.chi_inizia
            second = self.other(first)

            winner = winner_of_trick(
                first,
                self.played[first],
                second,
                self.played[second],
                self.seme_briscola,
            )

            loser = self.other(winner)

            points = self.played["p1"]["punti"] + self.played["p2"]["punti"]
            self.points[winner] += points
            self.tricks[winner] += 1

            winner_name = self.players[winner].name
            self.status = f"Mano vinta da {winner_name}."

            self.played = {"p1": None, "p2": None}
            self.chi_inizia = None

            if self.deck:
                self.hands[winner].append(self.deck.pop(0))

                if self.deck:
                    self.hands[loser].append(self.deck.pop(0))
                elif self.briscola_fisica:
                    self.hands[loser].append(self.briscola_fisica)
                    self.briscola_fisica = None

            elif self.briscola_fisica:
                self.hands[winner].append(self.briscola_fisica)
                self.briscola_fisica = None

            self.turn = winner
            self.resolving = False

            if not self.hands["p1"] and not self.hands["p2"]:
                round_winner = None
                if self.points["p1"] > self.points["p2"]:
                    round_winner = "p1"
                    self.match_wins["p1"] += 1
                elif self.points["p2"] > self.points["p1"]:
                    round_winner = "p2"
                    self.match_wins["p2"] += 1

                if self.match_target > 1:
                    if round_winner:
                        round_status = f"Partita {self.round_number} vinta da {self.players[round_winner].name}."
                    else:
                        round_status = f"Partita {self.round_number} finita in pareggio."

                    if self.match_wins["p1"] >= self.match_target or self.match_wins["p2"] >= self.match_target:
                        self.game_over = True
                        winner = "p1" if self.match_wins["p1"] > self.match_wins["p2"] else "p2"
                        self.status = f"Match finito: ha vinto {self.players[winner].name}."
                    else:
                        self.round_number += 1
                        self.start_round()
                        self.status = (
                            f"{round_status} "
                            f"Score match: {self.players['p1'].name} {self.match_wins['p1']} - "
                            f"{self.players['p2'].name} {self.match_wins['p2']}. "
                            f"Nuova partita: tocca a {self.players[self.turn].name}."
                        )
                else:
                    self.game_over = True
                    if self.points["p1"] > self.points["p2"]:
                        self.status = "Partita finita: ha vinto il giocatore 1."
                    elif self.points["p2"] > self.points["p1"]:
                        self.status = "Partita finita: ha vinto il giocatore 2."
                    else:
                        self.status = "Partita finita: pareggio."
            else:
                self.status += f" Tocca a {self.players[self.turn].name}."

    def public_state_for(self, seat: str) -> dict[str, Any]:
        other = self.other(seat)
        opponent_name = self.players[other].name if other in self.players else "Avversario"
        your_name = self.players[seat].name if seat in self.players else "Tu"
        deck_count = len(self.deck) + (1 if self.briscola_fisica else 0)

        return {
            "type": "state",
            "room": self.code,
            "started": self.started,
            "seat": seat,
            "your_name": your_name,
            "opponent_name": opponent_name,
            "your_hand": [c["id"] for c in self.hands[seat]],
            "opponent_count": len(self.hands[other]),
            "played_you": self.played[seat]["id"] if self.played[seat] else None,
            "played_opponent": self.played[other]["id"] if self.played[other] else None,
            "briscola_card": self.briscola_fisica["id"] if self.briscola_fisica else None,
            "briscola_seme": self.seme_briscola,
            "deck_count": deck_count,
            "your_tricks": self.tricks[seat],
            "opponent_tricks": self.tricks[other],
            "your_points": self.points[seat],
            "opponent_points": self.points[other],
            "turn_is_you": self.turn == seat and self.started and not self.game_over and not self.resolving,
            "waiting": not self.started,
            "status": self.status,
            "game_over": self.game_over,
            "disconnect": self.disconnected or ("disconnesso" in (self.status or "").lower()),
            "is_host": seat == "p1",
            "animations_enabled": self.animations_enabled,
            "animation_speed": self.animation_speed,
            "match_target": self.match_target,
            "match_score_you": self.match_wins.get(seat, 0),
            "match_score_opponent": self.match_wins.get(other, 0),
            "round_number": self.round_number,
            "rematch_you": seat in self.rematch_votes,
            "rematch_opponent": other in self.rematch_votes,
            "last_chat": self.last_chat,
        }


class BriscolaServer:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.lock = asyncio.Lock()

    def normalize_custom_room_code(self, raw: str) -> str:
        code = (raw or "").strip()

        if not code:
            return ""

        # Per evitare codici ingestibili:
        # - niente spazi
        # - niente simboli strani
        # - massimo 20 caratteri
        # - case-insensitive: "Casa" e "CASA" sono la stessa stanza.
        code = code.upper()

        if len(code) < 3:
            raise ValueError("Il codice stanza deve avere almeno 3 caratteri.")

        if len(code) > 20:
            raise ValueError("Il codice stanza può avere al massimo 20 caratteri.")

        if not re.fullmatch(r"[A-Z0-9_-]+", code):
            raise ValueError("Il codice stanza può contenere solo lettere, numeri, trattino e underscore.")

        return code

    def new_room_code(self) -> str:
        while True:
            code = str(random.randint(100000, 999999))

            if code not in self.rooms:
                return code

    async def send_error(self, client: Client, message: str) -> None:
        await client.send({"type": "error", "message": message})

    async def broadcast(self, room: Room) -> None:
        for seat, client in list(room.players.items()):
            if not client.alive:
                continue

            try:
                state = room.public_state_for(seat)
                ok = await client.send(state)

                if not ok:
                    print(f"[broadcast] invio fallito a {seat} nella stanza {room.code}")

            except Exception as exc:
                print(f"[broadcast-error] seat={seat} room={room.code}: {exc}")
                client.alive = False

    async def handle_create(self, client: Client, msg: dict[str, Any]) -> None:
        name = (msg.get("name") or "Giocatore 1").strip() or "Giocatore 1"

        try:
            requested_code = self.normalize_custom_room_code(str(msg.get("room") or ""))
        except ValueError as exc:
            await self.send_error(client, str(exc))
            return

        async with self.lock:
            code = requested_code or self.new_room_code()

            if code in self.rooms:
                await self.send_error(client, "Esiste già una stanza con questo codice.")
                return

            match_target = int(msg.get("match_target") or 1)
            if match_target not in [1, 2, 3]:
                match_target = 1

            speed = str(msg.get("animation_speed") or "Normale")
            if speed not in ["Lenta", "Normale", "Veloce"]:
                speed = "Normale"

            room = Room(
                code=code,
                match_target=match_target,
                animations_enabled=bool(msg.get("animations_enabled", True)),
                animation_speed=speed,
            )
            self.rooms[code] = room

            client.name = name
            client.room_code = code
            client.seat = "p1"
            room.players["p1"] = client

        print(f"[create] stanza {code} creata da {name}")
        await self.broadcast(room)

    async def handle_join(self, client: Client, msg: dict[str, Any]) -> None:
        try:
            code = self.normalize_custom_room_code(str(msg.get("room") or ""))
        except ValueError as exc:
            await self.send_error(client, str(exc))
            return

        name = (msg.get("name") or "Giocatore 2").strip() or "Giocatore 2"

        async with self.lock:
            room = self.rooms.get(code)

            if not room:
                await self.send_error(client, "Stanza non trovata.")
                return

            async with room.lock:
                if "p2" in room.players and room.players["p2"].alive:
                    await self.send_error(client, "Stanza già piena.")
                    return

                if "p1" not in room.players or not room.players["p1"].alive:
                    await self.send_error(client, "Il creatore della stanza non è più connesso.")
                    return

                client.name = name
                client.room_code = code
                client.seat = "p2"
                room.players["p2"] = client
                room.start()

        print(f"[join] {name} entrato nella stanza {code}")
        await self.broadcast(room)

    async def handle_play(self, client: Client, msg: dict[str, Any]) -> None:
        room = self.rooms.get(client.room_code or "")

        if not room:
            await self.send_error(client, "Partita non trovata.")
            return

        ok, status = await room.play_card(client.seat, str(msg.get("card_id") or ""))

        if not ok:
            await self.send_error(client, status)
            await self.broadcast(room)
            return

        await self.broadcast(room)

        if status == "resolve":
            asyncio.create_task(self.resolve_later(room))

    async def resolve_later(self, room: Room) -> None:
        await asyncio.sleep(1.0)
        await room.resolve_trick()
        await self.broadcast(room)

    async def handle_disconnect(self, client: Client) -> None:
        client.alive = False
        room = self.rooms.get(client.room_code or "")

        if not room:
            return

        async with room.lock:
            if client.seat in room.players and room.players[client.seat] is client:
                room.players.pop(client.seat, None)

            if room.players:
                room.status = "L'avversario si è disconnesso. La partita online è stata interrotta."
                room.disconnected = True
                room.game_over = True
            else:
                self.rooms.pop(room.code, None)
                print(f"[cleanup] stanza {room.code} rimossa")
                return

        await self.broadcast(room)

    async def handle_settings(self, client: Client, msg: dict[str, Any]) -> None:
        room = self.rooms.get(client.room_code or "")

        if not room:
            await self.send_error(client, "Partita non trovata.")
            return

        if client.seat != "p1":
            await self.send_error(client, "Solo chi ha creato la stanza può modificare le animazioni.")
            await self.broadcast(room)
            return

        enabled = bool(msg.get("animations_enabled", True))
        speed = str(msg.get("animation_speed") or "Normale")

        if speed not in ["Lenta", "Normale", "Veloce"]:
            speed = "Normale"

        async with room.lock:
            room.animations_enabled = enabled
            room.animation_speed = speed
            room.status = f"Animazioni: {'ON' if enabled else 'OFF'} - {speed}."

        await self.broadcast(room)

    async def handle_rematch(self, client: Client) -> None:
        room = self.rooms.get(client.room_code or "")

        if not room:
            await self.send_error(client, "Partita non trovata.")
            return

        async with room.lock:
            if room.disconnected:
                await self.send_error(client, "Non è possibile fare rivincita: l'avversario si è disconnesso.")
                return

            if not room.game_over:
                await self.send_error(client, "La rivincita si può chiedere solo a partita finita.")
                return

            if client.seat not in ["p1", "p2"]:
                await self.send_error(client, "Giocatore non valido.")
                return

            room.rematch_votes.add(client.seat)
            other = room.other(client.seat)

            if other in room.players and other in room.rematch_votes:
                room.start()
                room.status = "Rivincita accettata. Nuova partita iniziata."
            else:
                room.status = f"{client.name} vuole la rivincita."

        await self.broadcast(room)

    async def handle_chat(self, client: Client, msg: dict[str, Any]) -> None:
        room = self.rooms.get(client.room_code or "")

        if not room:
            await self.send_error(client, "Partita non trovata.")
            return

        text = str(msg.get("message") or "")
        text = re.sub(r"[\r\n\t]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            await self.send_error(client, "Messaggio vuoto.")
            return

        if len(text) > 160:
            text = text[:160]

        async with room.lock:
            room.chat_seq += 1
            room.last_chat = {
                "id": room.chat_seq,
                "from": client.seat,
                "name": client.name,
                "text": text,
            }

            # Il messaggio resta anche nello status, così si vede subito.
            room.status = f"{client.name}: {text}"

        await self.broadcast(room)

    async def handle_message(self, client: Client, msg: dict[str, Any]) -> None:
        typ = msg.get("type")

        if typ == "create":
            await self.handle_create(client, msg)
        elif typ == "join":
            await self.handle_join(client, msg)
        elif typ == "play":
            await self.handle_play(client, msg)
        elif typ == "settings":
            await self.handle_settings(client, msg)
        elif typ == "rematch":
            await self.handle_rematch(client)
        elif typ == "chat":
            await self.handle_chat(client, msg)
        elif typ == "ping":
            await client.send({"type": "pong"})
        else:
            await self.send_error(client, f"Comando sconosciuto: {typ}")


server = BriscolaServer()
app = FastAPI()


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "ok",
        "name": "Briscola online server",
        "websocket": "/ws",
    }


@app.head("/")
async def root_head():
    return None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    client = Client(websocket=websocket)
    print("[ws] client connesso")

    try:
        while True:
            msg = await websocket.receive_json()
            print(f"[msg] {msg}")
            await server.handle_message(client, msg)

    except WebSocketDisconnect:
        print("[ws] client disconnesso")

    except Exception as exc:
        print(f"[ws-error] {exc}")
        try:
            await client.send({"type": "error", "message": f"Errore server: {exc}"})
        except Exception:
            pass

    finally:
        await server.handle_disconnect(client)


if __name__ == "__main__":
    print(f"Server Briscola online FastAPI in ascolto su {HOST}:{PORT}")
    print("HTTP check: /")
    print("WebSocket: /ws")
    uvicorn.run(app, host=HOST, port=PORT)
