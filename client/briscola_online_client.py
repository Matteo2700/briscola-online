
import json
import re
import threading
import websocket
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from PIL import Image, ImageTk

SEMI = ["coppe", "denari", "spade", "bastoni"]
VALORI = [
    ("asso", 11, 10), ("3", 10, 9), ("re", 4, 8), ("cavallo", 3, 7),
    ("fante", 2, 6), ("7", 0, 5), ("6", 0, 4), ("5", 0, 3), ("4", 0, 2), ("2", 0, 1),
]

CARD_W = 80
CARD_H = 160
BG = "#052b18"
TABLE = "#0b6b34"
TABLE_DARK = "#074823"
TABLE_LIGHT = "#159447"
GOLD = "#f4d35e"
WHITE = "#ffffff"
MUTED = "#bfe8c5"
BLACKISH = "#03170d"
ICON_FILES = ["icona.ico", "icon.ico", "icona.png", "icon.png"]

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS

class Carta:
    def __init__(self, seme, nome, punti, forza):
        self.seme = seme
        self.nome = nome
        self.punti = punti
        self.forza = forza
        self.id = f"{seme}_{nome}"
        img = Image.open(f"carte/{seme}_{nome}.png").resize((CARD_W, CARD_H), RESAMPLE)
        self.img = ImageTk.PhotoImage(img)

class DummyDeck:
    def __init__(self, count=0):
        self.carte = [None] * max(0, int(count))

class OnlineBriscolaClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Briscola Online")
        self.root.geometry("1300x720")
        self.root.configure(bg=BG)
        try:
            self.root.state("zoomed")
        except Exception:
            pass

        self.app_icon = None
        self.load_window_icon()

        self.ws = None
        self.connected = False
        self.room_code = ""
        self.seat = None
        self.status = "Non connesso."
        self.game_over_shown = False

        self.card_map = {}
        for s in SEMI:
            for n, p, f in VALORI:
                c = Carta(s, n, p, f)
                self.card_map[c.id] = c

        self.back_img = ImageTk.PhotoImage(Image.open("carte/retro.png").resize((CARD_W, CARD_H), RESAMPLE))
        self.back_small = ImageTk.PhotoImage(Image.open("carte/retro.png").resize((36, 72), RESAMPLE))

        self.player = []
        self.bot = []
        self.c_p = None
        self.c_b = None
        self.briscola_fisica = None
        self.seme_briscola = ""
        self.deck = DummyDeck(0)
        self.mani_p = 0
        self.mani_b = 0
        self.punti_p = 0
        self.punti_b = 0
        self.turn_player = False
        self.lock = True
        self.opponent_name = "Avversario"
        self.your_name = "Tu"
        self.pos = {}
        self.animating = False
        self.pending_state = None
        self.suppress_next_own_animation_id = None

        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render())

        self.setup_menu()
        self.show_connect_dialog()
        self.render()

    def load_window_icon(self):
        for icon_name in ICON_FILES:
            path = Path(icon_name)
            if not path.exists():
                continue
            try:
                if path.suffix.lower() == ".ico":
                    self.root.iconbitmap(str(path))
                    return
                img = Image.open(path).resize((256, 256), RESAMPLE)
                self.app_icon = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self.app_icon)
                return
            except Exception:
                pass

    def setup_menu(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)
        m = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Online", menu=m)
        m.add_command(label="Connetti / cambia stanza", command=self.show_connect_dialog)
        m.add_separator()
        m.add_command(label="Esci", command=self.root.destroy)

    def normalize_server_url(self, raw):
        url = (raw or "").strip()

        if not url:
            raise ValueError("Server URL vuoto.")

        if url.startswith("http://"):
            url = "ws://" + url[len("http://"):]
        elif url.startswith("https://"):
            url = "wss://" + url[len("https://"):]
        elif not (url.startswith("ws://") or url.startswith("wss://")):
            # Comodo per test locali: localhost:8765 diventa ws://localhost:8765
            url = "ws://" + url

        url = url.rstrip("/")

        # Il nuovo server FastAPI espone il WebSocket su /ws.
        # Se l'utente inserisce solo il dominio Render, lo aggiungiamo noi.
        if not url.endswith("/ws"):
            url += "/ws"

        return url

    def send(self, obj):
        if not self.ws:
            messagebox.showerror("Online", "Non sei connesso al server.")
            return

        try:
            self.ws.send(json.dumps(obj, ensure_ascii=False))
        except Exception as e:
            messagebox.showerror("Online", f"Errore invio dati:\n{e}")

    def receiver_thread(self):
        close_reason = "Connessione chiusa."

        try:
            while True:
                raw = self.ws.recv()

                if not raw:
                    break

                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                self.root.after(0, lambda m=msg: self.handle_message(m))

        except Exception as exc:
            close_reason = f"Connessione chiusa: {exc}"

        self.root.after(0, lambda r=close_reason: self.set_status(r))

    def connect(self, server_url):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

        url = self.normalize_server_url(server_url)
        # timeout=10 serve solo per il tentativo iniziale di connessione.
        # Dopo la connessione lo togliamo, altrimenti ws.recv() va in timeout
        # dopo 10 secondi senza messaggi e il client mostra "Connessione chiusa".
        self.ws = websocket.create_connection(url, timeout=10)
        self.ws.settimeout(None)

        self.connected = True
        self.game_over_shown = False
        threading.Thread(target=self.receiver_thread, daemon=True).start()

    def show_connect_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Briscola online")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        if self.app_icon:
            try:
                dialog.iconphoto(True, self.app_icon)
            except Exception:
                pass

        main = ttk.Frame(dialog, padding=(18, 16, 18, 14))
        main.pack(fill="both", expand=True)

        mode = tk.StringVar(value="create")
        name_var = tk.StringVar(value="")
        server_var = tk.StringVar(value="wss://briscola-online-wh5m.onrender.com/ws")
        room_var = tk.StringVar(value="")

        ttk.Label(main, text="Partita online", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(main, text="Nome").grid(row=1, column=0, sticky="w")
        name_entry = ttk.Entry(main, textvariable=name_var, width=26)
        name_entry.grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(main, text="Server URL").grid(row=2, column=0, sticky="w")
        ttk.Entry(main, textvariable=server_var, width=42).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(
            main,
            text="Esempio: wss://nome-servizio.onrender.com/ws",
            font=("Segoe UI", 8)
        ).grid(row=3, column=1, sticky="w", pady=(0, 4))

        lf = ttk.LabelFrame(main, text="Modalità", padding=(10,8,10,8))
        lf.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Radiobutton(lf, text="Crea nuova stanza", variable=mode, value="create").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(lf, text="Entra in stanza", variable=mode, value="join").grid(row=1, column=0, sticky="w")
        ttk.Label(lf, text="Codice stanza").grid(row=2, column=0, sticky="w", pady=(8,0))
        room_entry = ttk.Entry(lf, textvariable=room_var, width=20)
        room_entry.grid(row=2, column=1, sticky="w", padx=(8,0), pady=(8,0))

        ttk.Label(
            lf,
            text="Se crei: vuoto = automatico",
            font=("Segoe UI", 8)
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        buttons = ttk.Frame(main)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12,0))

        def go():
            nome = name_var.get().strip()

            if not nome:
                messagebox.showwarning("Nome richiesto", "Inserisci un nome prima di iniziare.")
                name_entry.focus_set()
                return

            if mode.get() == "join" and not room_var.get().strip():
                messagebox.showwarning("Codice stanza richiesto", "Inserisci il codice stanza.")
                room_entry.focus_set()
                return

            try:
                self.connect(server_var.get().strip())

                room_code = room_var.get().strip()

                if mode.get() == "create":
                    # Se room_code è vuoto, il server genera un codice automatico.
                    # Se è compilato, prova a creare la stanza con quel codice personalizzato.
                    self.send({"type": "create", "name": nome, "room": room_code})
                else:
                    self.send({"type": "join", "name": nome, "room": room_code})

                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Online", f"Connessione fallita:\n{e}")

        ttk.Button(buttons, text="Connetti", command=go).pack(side="right", padx=(8,0))
        ttk.Button(buttons, text="Annulla", command=dialog.destroy).pack(side="right")
        name_entry.focus_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
        dialog.geometry(f"+{x}+{y}")

    def handle_message(self, msg):
        if msg.get("type") == "error":
            messagebox.showerror("Online", msg.get("message", "Errore sconosciuto"))
            return
        if msg.get("type") != "state":
            return
        self.apply_state(msg)

    def set_status(self, text):
        self.status = self.translate_server_status(text)
        self.render()

    def card(self, cid):
        return self.card_map.get(cid) if cid else None

    def set_state_from_server(self, st):
        self.room_code = st.get("room", "")
        self.seat = st.get("seat")
        self.your_name = (st.get("your_name") or "Tu").strip() or "Tu"
        self.opponent_name = (st.get("opponent_name") or "Avversario").strip() or "Avversario"

        self.player = [self.card(cid) for cid in st.get("your_hand", []) if self.card(cid)]
        self.bot = [None] * int(st.get("opponent_count", 0))

        self.c_p = self.card(st.get("played_you"))
        self.c_b = self.card(st.get("played_opponent"))

        self.briscola_fisica = self.card(st.get("briscola_card"))
        self.seme_briscola = st.get("briscola_seme") or ""

        self.deck = DummyDeck(st.get("deck_count", 0))

        self.mani_p = int(st.get("your_tricks", 0))
        self.mani_b = int(st.get("opponent_tricks", 0))
        self.punti_p = int(st.get("your_points", 0))
        self.punti_b = int(st.get("opponent_points", 0))

        self.turn_player = bool(st.get("turn_is_you", False))
        self.lock = not self.turn_player
        self.status = self.translate_server_status(st.get("status", ""))

        # Se il server ha confermato la carta giocata localmente,
        # non serve più sopprimere l'animazione.
        if self.c_p and self.suppress_next_own_animation_id == self.c_p.id:
            self.suppress_next_own_animation_id = None

        self.render()

        if st.get("game_over") and not self.game_over_shown:
            self.game_over_shown = True

            if self.punti_p > self.punti_b:
                res = "Hai vinto!"
            elif self.punti_p < self.punti_b:
                res = "Hai perso!"
            else:
                res = "Pareggio!"

            messagebox.showinfo(
                "Fine partita",
                f"{res}\n\n"
                f"{self.your_name}: {self.punti_p} | {self.opponent_name}: {self.punti_b}"
            )

    def translate_server_status(self, status):
        status = status or ""

        if not self.seat:
            return status

        if self.seat == "p1":
            p1_name = self.your_name
            p2_name = self.opponent_name
        else:
            p1_name = self.opponent_name
            p2_name = self.your_name

        # Prima gestisco le frasi complete, così non viene fuori
        # "Tocca al Matteo", che fa venire voglia di spegnere il PC.
        status = status.replace("Tocca al giocatore 1", f"Tocca a {p1_name}")
        status = status.replace("Tocca al giocatore 2", f"Tocca a {p2_name}")
        status = status.replace("tocca al giocatore 1", f"tocca a {p1_name}")
        status = status.replace("tocca al giocatore 2", f"tocca a {p2_name}")

        status = status.replace("Tocca a giocatore 1", f"Tocca a {p1_name}")
        status = status.replace("Tocca a giocatore 2", f"Tocca a {p2_name}")
        status = status.replace("tocca a giocatore 1", f"tocca a {p1_name}")
        status = status.replace("tocca a giocatore 2", f"tocca a {p2_name}")

        replacements = {
            "giocatore 1": p1_name,
            "Giocatore 1": p1_name,
            "giocatore 2": p2_name,
            "Giocatore 2": p2_name,
        }

        for old, new in replacements.items():
            status = status.replace(old, new)

        # Regola grafica: i punti si vedono SOLO nel riepilogo finale.
        # Quindi nello status online tolgo frasi tipo "(+10)".
        status = re.sub(r"\s*\(\+\d+\)", "", status)

        return status

    def apply_state(self, st):
        if self.animating:
            self.pending_state = st
            return

        new_c_p = self.card(st.get("played_you"))
        new_c_b = self.card(st.get("played_opponent"))

        old_c_p = self.c_p
        old_c_b = self.c_b
        old_mani_p = self.mani_p
        old_mani_b = self.mani_b
        old_player_ids = [c.id for c in self.player if c]
        old_player_count = len(self.player)
        old_bot_count = len(self.bot)

        # 1) Risoluzione mano: prima faccio volare le carte vinte nel box mani vinte,
        # poi applico lo stato nuovo arrivato dal server.
        if old_c_p and old_c_b and not new_c_p and not new_c_b:
            new_mani_p = int(st.get("your_tricks", 0))
            new_mani_b = int(st.get("opponent_tricks", 0))

            winner = None

            if new_mani_p > old_mani_p:
                winner = "player"
                target = self.pos.get("player_pile")
            elif new_mani_b > old_mani_b:
                winner = "bot"
                target = self.pos.get("bot_pile")
            else:
                target = None

            if target:
                src_p = self.pos.get("played_player")
                src_b = self.pos.get("played_bot")

                if src_p and src_b:
                    self.animating = True
                    self.animate_two_cards_to_target(
                        old_c_p.img,
                        src_p,
                        old_c_b.img,
                        src_b,
                        target,
                        lambda: self.finish_trick_animation_with_draws(
                            st,
                            winner,
                            old_player_ids,
                            old_player_count,
                            old_bot_count
                        )
                    )
                    return

        # 2) Carta dell'avversario giocata: la faccio scendere dalla mano avversaria allo slot.
        if not old_c_b and new_c_b:
            src = self.pos.get("opponent_hand_source")
            dst = self.pos.get("played_bot")

            if src and dst:
                self.animating = True
                self.animate_card_move(
                    new_c_b.img,
                    src,
                    dst,
                    lambda: self.finish_animation_with_state(st)
                )
                return

        # 3) Tua carta giocata da conferma server.
        # Normalmente l'abbiamo già animata localmente in on_move;
        # questa parte serve solo se arriva uno stato non previsto.
        if not old_c_p and new_c_p and self.suppress_next_own_animation_id != new_c_p.id:
            src = self.pos.get("player_hand_source")
            dst = self.pos.get("played_player")

            if src and dst:
                self.animating = True
                self.animate_card_move(
                    new_c_p.img,
                    src,
                    dst,
                    lambda: self.finish_animation_with_state(st)
                )
                return

        self.set_state_from_server(st)

    def finish_trick_animation_with_draws(self, st, winner, old_player_ids, old_player_count, old_bot_count):
        """
        Dopo l'animazione delle carte vinte, anima anche la pesca.
        Poi applica lo stato definitivo ricevuto dal server.
        """
        # Svuoto visivamente gli slot centrali prima della pesca.
        self.c_p = None
        self.c_b = None
        self.render()

        new_player_ids = list(st.get("your_hand", []))
        new_player_count = len(new_player_ids)
        new_bot_count = int(st.get("opponent_count", 0))

        player_drew = new_player_count > old_player_count
        bot_drew = new_bot_count > old_bot_count

        draw_jobs = []

        added_player_ids = [cid for cid in new_player_ids if cid not in old_player_ids]
        player_card = self.card(added_player_ids[0]) if added_player_ids else None

        if player_drew:
            draw_jobs.append(("player", player_card.img if player_card else self.back_img))

        if bot_drew:
            draw_jobs.append(("bot", self.back_img))

        # Ordine corretto: chi ha vinto la mano pesca per primo.
        if winner == "bot":
            draw_jobs.sort(key=lambda item: 0 if item[0] == "bot" else 1)
        else:
            draw_jobs.sort(key=lambda item: 0 if item[0] == "player" else 1)

        if not draw_jobs:
            self.finish_animation_with_state(st)
            return

        self.animate_draw_sequence(
            draw_jobs,
            lambda: self.finish_animation_with_state(st)
        )

    def animate_draw_sequence(self, draw_jobs, callback):
        if not draw_jobs:
            callback()
            return

        owner, img = draw_jobs[0]

        # In genere si pesca dal mazzo; se il mazzo è visivamente vuoto ma c'è
        # ancora la briscola fisica, parto dalla posizione briscola.
        src = self.pos.get("deck", (110, 260))

        if owner == "player":
            dst = self.pos.get("player_draw_target", (500, 470))
        else:
            dst = self.pos.get("opponent_draw_target", (500, 82))

        def next_one():
            self.animate_draw_sequence(draw_jobs[1:], callback)

        self.animate_card_move(img, src, dst, next_one)

    def finish_animation_with_state(self, st):
        self.animating = False
        self.canvas.delete("anim")
        self.set_state_from_server(st)

        if self.pending_state is not None:
            next_state = self.pending_state
            self.pending_state = None
            self.root.after(50, lambda: self.apply_state(next_state))

    def get_animation_steps(self):
        return 14

    def animate_card_move(self, img, src, dst, callback):
        sx, sy = src
        dx, dy = dst
        steps = self.get_animation_steps()

        anim_id = self.canvas.create_image(sx, sy, image=img, anchor="nw", tags="anim")

        def step(i):
            if i >= steps:
                self.canvas.delete(anim_id)
                callback()
                return

            self.canvas.move(anim_id, (dx - sx) / steps, (dy - sy) / steps)
            self.root.after(18, lambda: step(i + 1))

        step(0)

    def animate_two_cards_to_target(self, img1, src1, img2, src2, dst, callback):
        sx1, sy1 = src1
        sx2, sy2 = src2
        dx, dy = dst
        steps = self.get_animation_steps()

        a1 = self.canvas.create_image(sx1, sy1, image=img1, anchor="nw", tags="anim")
        a2 = self.canvas.create_image(sx2, sy2, image=img2, anchor="nw", tags="anim")

        def step(i):
            if i >= steps:
                self.canvas.delete(a1)
                self.canvas.delete(a2)
                callback()
                return

            self.canvas.move(a1, (dx - sx1) / steps, (dy - sy1) / steps)
            self.canvas.move(a2, (dx - sx2) / steps, (dy - sy2) / steps)

            self.root.after(18, lambda: step(i + 1))

        step(0)

    def rounded_rect(self, x1, y1, x2, y2, r=24, **kwargs):
        points = [x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def draw_text(self, x, y, text, size=14, color=WHITE, weight="normal", anchor="center"):
        return self.canvas.create_text(x, y, text=text, fill=color, font=("Segoe UI", size, weight), anchor=anchor)

    def draw_card(self, x, y, img, tag=None, outline=None):
        tags = tag if tag else ""
        self.canvas.create_rectangle(x+5, y+7, x+CARD_W+5, y+CARD_H+7, fill="#02130a", outline="", tags=tags)
        if outline:
            self.canvas.create_rectangle(x-4, y-4, x+CARD_W+4, y+CARD_H+4, outline=outline, width=3, tags=tags)
        return self.canvas.create_image(x, y, image=img, anchor="nw", tags=tags)

    def draw_empty_slot(self, x, y, label="", active=False):
        color = GOLD if active else TABLE_LIGHT
        self.canvas.create_rectangle(x, y, x+CARD_W, y+CARD_H, fill=TABLE_DARK, outline=color, width=2)
        if label:
            self.draw_text(x+CARD_W/2, y+CARD_H/2, label, size=10, color=MUTED, weight="bold")

    def render(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width() if self.canvas.winfo_width() > 100 else 1300
        h = self.canvas.winfo_height() if self.canvas.winfo_height() > 100 else 720
        cx = w / 2
        self.canvas.create_rectangle(0, 0, w, h, fill=BG, outline="")
        self.rounded_rect(45, 24, w-45, h-24, r=50, fill=TABLE, outline="#0f9d4e", width=5)

        player_y = h - CARD_H - 48
        gap = 34
        box_pad_y = 18
        played_y = player_y - gap - CARD_H - box_pad_y
        bot_y = played_y - box_pad_y - gap - CARD_H
        if bot_y < 38:
            delta = 38 - bot_y
            bot_y += delta
            played_y += delta

        played_bot_x = cx - CARD_W - 20
        played_player_x = cx + 20
        deck_x = 110
        deck_y = played_y
        briscola_x = deck_x + CARD_W + 45
        briscola_y = deck_y
        right_panel_x = w - 335

        self.pos["deck"] = (deck_x, deck_y)
        self.pos["briscola"] = (briscola_x, briscola_y)
        self.pos["played_bot"] = (played_bot_x, played_y)
        self.pos["played_player"] = (played_player_x, played_y)
        self.pos["opponent_hand_source"] = (cx - CARD_W / 2, bot_y)
        self.pos["player_hand_source"] = (cx - CARD_W / 2, player_y)
        self.pos["opponent_draw_target"] = (cx - CARD_W / 2, bot_y)
        self.pos["player_draw_target"] = (cx - CARD_W / 2, player_y)
        self.pos["bot_pile"] = (right_panel_x + 198, 105 + 28)
        self.pos["player_pile"] = (right_panel_x + 198, h - 165 + 28)

        center_x1 = played_bot_x - 24
        center_y1 = played_y - box_pad_y
        center_x2 = played_player_x + CARD_W + 24
        center_y2 = played_y + CARD_H + box_pad_y
        self.rounded_rect(center_x1, center_y1, center_x2, center_y2, r=26, fill=TABLE_DARK, outline=TABLE_LIGHT, width=2)

        self.rounded_rect(75, deck_y-52, briscola_x+CARD_W+35, deck_y+CARD_H+55, r=24, fill=BLACKISH, outline="#1ca956", width=2)
        self.draw_text(deck_x+CARD_W/2, deck_y-29, "MAZZO", size=11, color=GOLD, weight="bold")
        self.draw_text(briscola_x+CARD_W/2, briscola_y-29, "BRISCOLA", size=11, color=GOLD, weight="bold")
        self.draw_text(deck_x+CARD_W/2, deck_y+CARD_H+26, f"{len(self.deck.carte)} carte", size=10, color=WHITE, weight="bold")
        if len(self.deck.carte) > 0:
            self.draw_card(deck_x, deck_y, self.back_img, outline=TABLE_LIGHT)
        else:
            self.draw_empty_slot(deck_x, deck_y, "VUOTO")
        if self.briscola_fisica:
            self.draw_card(briscola_x, briscola_y, self.briscola_fisica.img, outline=TABLE_LIGHT)
            self.draw_text(briscola_x+CARD_W/2, briscola_y+CARD_H+26, self.seme_briscola.upper(), size=11, color=GOLD, weight="bold")
        else:
            self.draw_empty_slot(briscola_x, briscola_y, "")
            if self.seme_briscola:
                self.draw_text(briscola_x+CARD_W/2, briscola_y+CARD_H+26, self.seme_briscola.upper(), size=11, color=GOLD, weight="bold")

        self.draw_score_panel(right_panel_x, 105, self.opponent_name.upper(), self.mani_b)
        self.draw_score_panel(right_panel_x, h-165, self.your_name.upper(), self.mani_p)

        # Pannello stato online: larghezza proporzionata al testo,
        # non una banda infinita sotto le carte.
        txt = "Online" + (f" | stanza {self.room_code}" if self.room_code else "")
        status_txt = self.status or ""

        approx_w = max(len(txt) * 9, len(status_txt) * 7) + 44
        panel_w = max(250, min(520, approx_w))

        self.rounded_rect(75, h-100, 75 + panel_w, h-45, r=17, fill=BLACKISH, outline="#1ca956", width=2)

        self.canvas.create_text(
            95,
            h-83,
            text=txt,
            fill=GOLD,
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        )

        self.canvas.create_text(
            95,
            h-62,
            text=status_txt,
            fill=MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
            width=panel_w - 35
        )

        self.draw_empty_slot(played_bot_x, played_y, "AVV", active=False)
        self.draw_empty_slot(played_player_x, played_y, "TU", active=self.turn_player)
        if self.c_b:
            self.draw_card(played_bot_x, played_y, self.c_b.img, tag="played", outline=GOLD)
        if self.c_p:
            self.draw_card(played_player_x, played_y, self.c_p.img, tag="played", outline=GOLD)

        self.draw_hand(self.bot, cx, bot_y, owner="bot")
        self.draw_hand(self.player, cx, player_y, owner="player")

    def draw_score_panel(self, x, y, title, mani):
        panel_w = 250
        panel_h = 112

        title = str(title or "").strip() or "GIOCATORE"

        # Font dinamico: niente troncamento brutale dei nomi lunghi.
        if len(title) <= 10:
            title_size = 15
        elif len(title) <= 14:
            title_size = 13
        elif len(title) <= 18:
            title_size = 11
        else:
            title_size = 10

        self.rounded_rect(x, y, x + panel_w, y + panel_h, r=22, fill=BLACKISH, outline=GOLD, width=2)

        self.canvas.create_text(
            x + panel_w / 2,
            y + 25,
            text=title,
            fill=GOLD,
            font=("Segoe UI", title_size, "bold"),
            anchor="center",
            width=panel_w - 22
        )

        if mani <= 0:
            self.draw_text(
                x + panel_w / 2,
                y + 73,
                "Mani vinte: 0",
                size=12,
                color=WHITE,
                weight="bold"
            )
            return

        self.draw_text(
            x + 88,
            y + 73,
            f"Mani vinte: {mani}",
            size=12,
            color=WHITE,
            weight="bold"
        )

        # Dorsino più a destra, dentro al pannello, senza coprire il nome.
        self.canvas.create_image(
            x + 195,
            y + 34,
            image=self.back_small,
            anchor="nw"
        )

    def draw_hand(self, cards, cx, y, owner):
        if not cards:
            return
        gap = 16
        total_w = len(cards) * CARD_W + (len(cards)-1) * gap
        start_x = cx - total_w / 2
        for i, c in enumerate(cards):
            x = start_x + i * (CARD_W + gap)
            self.pos[f"{owner}_card_{i}"] = (x, y)

            if owner == "player":
                tag = f"player_card_{i}"
                outline = GOLD if self.turn_player and not self.c_p else TABLE_LIGHT
                self.draw_card(x, y, c.img, tag=tag, outline=outline)
                self.canvas.tag_bind(tag, "<Button-1>", lambda event, idx=i: self.on_move(idx))
                self.canvas.tag_bind(tag, "<Enter>", lambda event: self.canvas.config(cursor="hand2"))
                self.canvas.tag_bind(tag, "<Leave>", lambda event: self.canvas.config(cursor=""))
            else:
                self.draw_card(x, y, self.back_img, outline=TABLE_LIGHT)

    def on_move(self, idx):
        if self.animating:
            return

        if not self.turn_player:
            return

        if idx < 0 or idx >= len(self.player):
            return

        card = self.player[idx]
        src = self.pos.get(f"player_card_{idx}")
        dst = self.pos.get("played_player")

        self.turn_player = False
        self.lock = True
        self.suppress_next_own_animation_id = card.id

        def after_local_animation():
            # Aggiornamento locale immediato: così la carta non sembra teletrasportata.
            if card in self.player:
                self.player.remove(card)

            self.c_p = card
            self.render()
            self.send({"type": "play", "card_id": card.id})

        if src and dst:
            self.animating = True

            def finish_local():
                self.animating = False
                self.canvas.delete("anim")
                after_local_animation()

            self.animate_card_move(card.img, src, dst, finish_local)
        else:
            after_local_animation()

if __name__ == "__main__":
    root = tk.Tk()
    OnlineBriscolaClient(root)
    root.mainloop()
