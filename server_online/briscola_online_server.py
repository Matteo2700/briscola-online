import asyncio
import json
import os
import random
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

    async def send(self, obj: dict[str, Any]) -> None:
        try:
            await self.websocket.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            self.alive = False


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
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def other(self, seat: str) -> str:
        return "p2" if seat == "p1" else "p1"

    def start(self) -> None:
        self.deck = make_deck()
        self.hands["p1"] = [self.deck.pop(0) for _ in range(3)]
        self.hands["p2"] = [self.deck.pop(0) for _ in range(3)]
        self.briscola_fisica = self.deck.pop()
        self.seme_briscola = self.briscola_fisica["seme"]
        self.turn = "p1"
        self.chi_inizia = None
        self.started = True
        self.game_over = False
        self.resolving = False
        self.status = "Tocca al giocatore 1."

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
            self.status = f"Mano vinta da {winner_name} (+{points})."

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
        }


class BriscolaServer:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.clients: set[Client] = set()
        self.lock = asyncio.Lock()

    def new_room_code(self) -> str:
        while True:
            code = str(random.randint(100000, 999999))

            if code not in self.rooms:
                return code

    async def send_error(self, client: Client, message: str) -> None:
        await client.send({"type": "error", "message": message})

    async def broadcast(self, room: Room) -> None:
        for seat, client in list(room.players.items()):
            if client.alive:
                await client.send(room.public_state_for(seat))

    async def handle_create(self, client: Client, msg: dict[str, Any]) -> None:
        name = (msg.get("name") or "Giocatore 1").strip() or "Giocatore 1"

        async with self.lock:
            code = self.new_room_code()
            room = Room(code=code)
            self.rooms[code] = room

            client.name = name
            client.room_code = code
            client.seat = "p1"
            room.players["p1"] = client

        await self.broadcast(room)

    async def handle_join(self, client: Client, msg: dict[str, Any]) -> None:
        code = str(msg.get("room") or "").strip()
        name = (msg.get("name") or "Giocatore 2").strip() or "Giocatore 2"

        async with self.lock:
            room = self.rooms.get(code)

            if not room:
                await self.send_error(client, "Stanza non trovata.")
                return

            async with room.lock:
                if "p2" in room.players:
                    await self.send_error(client, "Stanza già piena.")
                    return

                client.name = name
                client.room_code = code
                client.seat = "p2"
                room.players["p2"] = client
                room.start()

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
            other_seat = "p2" if client.seat == "p1" else "p1"

            if other_seat in room.players:
                room.status = "L'avversario si è disconnesso."
                room.game_over = True

        await self.broadcast(room)

    async def handle_message(self, client: Client, msg: dict[str, Any]) -> None:
        typ = msg.get("type")

        if typ == "create":
            await self.handle_create(client, msg)
        elif typ == "join":
            await self.handle_join(client, msg)
        elif typ == "play":
            await self.handle_play(client, msg)
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    client = Client(websocket=websocket)
    server.clients.add(client)

    try:
        while True:
            msg = await websocket.receive_json()
            await server.handle_message(client, msg)

    except WebSocketDisconnect:
        pass

    except Exception as exc:
        try:
            await client.send({"type": "error", "message": f"Errore server: {exc}"})
        except Exception:
            pass

    finally:
        await server.handle_disconnect(client)
        server.clients.discard(client)


if __name__ == "__main__":
    print(f"Server Briscola online FastAPI in ascolto su {HOST}:{PORT}")
    print("HTTP check: /")
    print("WebSocket: /ws")
    uvicorn.run(app, host=HOST, port=PORT)
