
import tkinter as tk
from tkinter import messagebox, ttk
import random
import json
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageTk

try:
    import pygame
except Exception:
    pygame = None


# ============================================================
# DATI
# ============================================================

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


# ============================================================
# GRAFICA
# ============================================================
# Più piccole della versione precedente, così non si incastra tutto.
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

STATS_FILE = "briscola_stats.json"
SETTINGS_FILE = "briscola_settings.json"
ICON_FILES = ["icona.ico", "icon.ico", "icona.png", "icon.png"]

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


# ============================================================
# CARTA
# ============================================================

class Carta:
    def __init__(self, seme, nome, punti, forza):
        self.seme = seme
        self.nome = nome
        self.punti = punti
        self.forza = forza

        img = Image.open(f"carte/{seme}_{nome}.png").resize((CARD_W, CARD_H), RESAMPLE)
        self.img = ImageTk.PhotoImage(img)

    def __repr__(self):
        return f"{self.nome} di {self.seme}"


# ============================================================
# MAZZO
# ============================================================

class Mazzo:
    def __init__(self):
        self.carte = [Carta(s, n, p, f) for s in SEMI for n, p, f in VALORI]
        self.mescola_per_bene()

    def mescola_per_bene(self):
        for _ in range(5):
            random.shuffle(self.carte)

        carichi_iniziali = sum(1 for c in self.carte[:6] if c.punti >= 10)

        if carichi_iniziali > 2:
            random.shuffle(self.carte)

    def pesca(self):
        return self.carte.pop(0) if self.carte else None

    def pesca_truccata(self, livello_avanzato, seme_briscola, mano_bot):
        if not self.carte:
            return None

        if not hasattr(self, "ultime_pesche_normali"):
            self.ultime_pesche_normali = 0

        carichi_in_mano = sum(1 for c in mano_bot if c and c.punti >= 10)

        if carichi_in_mano >= 2:
            self.ultime_pesche_normali += 1
            return self.pesca()

        briscole_disponibili = [c for c in self.carte if c.seme == seme_briscola]

        if livello_avanzato == "Avanzato":
            target = [c for c in briscole_disponibili if 0 < c.punti < 10]
            probabilita = 0.4
            cooldown = 2

        elif livello_avanzato == "Avanzato+":
            target = [c for c in briscole_disponibili if c.punti >= 10]
            probabilita = 0.5
            cooldown = 3

        elif livello_avanzato == "Avanzato++":
            carichi = [c for c in briscole_disponibili if c.punti >= 10]
            figure = [c for c in briscole_disponibili if 0 < c.punti < 10]
            lisce = [c for c in briscole_disponibili if c.punti == 0]
            lisce_scelte = random.sample(lisce, min(3, len(lisce))) if lisce else []

            target = carichi + figure + lisce_scelte
            probabilita = 0.6
            cooldown = 2

        else:
            return self.pesca()

        if self.ultime_pesche_normali >= cooldown and target and random.random() < probabilita:
            carta = random.choice(target)
            self.carte.remove(carta)
            self.ultime_pesche_normali = 0
            return carta

        self.ultime_pesche_normali += 1
        return self.pesca()


# ============================================================
# GIOCO
# ============================================================

class BriscolaGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Briscola")
        self.root.geometry("1300x720")
        self.root.configure(bg=BG)

        self.app_should_close = False
        self.app_icon = None

        try:
            self.root.state("zoomed")
        except Exception:
            pass

        self.load_window_icon()

        self.settings = self.load_settings()

        self.livello = tk.StringVar(value=self.settings.get("difficolta", "Medio"))
        self.livello_attivo = self.livello.get()

        self.debug_bot = tk.BooleanVar(value=bool(self.settings.get("debug_bot", False)))
        self.audio_enabled = tk.BooleanVar(value=bool(self.settings.get("audio_enabled", True)))
        self.animazioni_enabled = tk.BooleanVar(value=bool(self.settings.get("animazioni_enabled", True)))
        self.training_mode = tk.BooleanVar(value=bool(self.settings.get("training_mode", False)))
        self.velocita_animazioni = tk.StringVar(value=self.settings.get("velocita_animazioni", "Normale"))

        self.lock = False
        self.stats_recorded_for_current_game = False
        self.stats = self.load_stats()
        self.trofei_sbloccati_ultima_partita = []
        self.storico_mani = []
        self.bot_reason = ""
        self.training_tip = ""

        self.init_audio()

        if not self.validate_assets():
            self.app_should_close = True
            self.root.destroy()
            return

        self.back_img = ImageTk.PhotoImage(
            Image.open("carte/retro.png").resize((CARD_W, CARD_H), RESAMPLE)
        )

        self.back_small = ImageTk.PhotoImage(
            Image.open("carte/retro.png").resize((36, 72), RESAMPLE)
        )

        self.canvas = tk.Canvas(
            self.root,
            bg=BG,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.pos = {}
        self.animating_card_play = False

        self.setup_menu()

        self.root.bind("<n>", self.reset_game)
        self.root.bind("<N>", self.reset_game)
        self.root.bind("<e>", self.exit_game)
        self.root.bind("<E>", self.exit_game)

        self.canvas.bind("<Configure>", lambda e: self.render())

        self.scelta_difficolta_iniziale()

        if self.app_should_close:
            return

        self.start_game()

    # ========================================================
    # ICONA E STATISTICHE
    # ========================================================

    def load_window_icon(self):
        """
        Carica l'icona del programma se trova uno di questi file
        nella stessa cartella del gioco:
        - icona.ico
        - icon.ico
        - icona.png
        - icon.png

        Per Windows va benissimo anche .ico.
        Per Tkinter va benissimo anche .png con iconphoto.
        """

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
                # Se l'icona non è valida, il gioco parte comunque.
                pass

    def get_default_stats(self):
        return {
            "partite": 0,
            "vittorie": 0,
            "sconfitte": 0,
            "pareggi": 0,

            "winstreak_attuale": 0,
            "winstreak_migliore": 0,
            "losestreak_attuale": 0,
            "losestreak_migliore": 0,

            "punti_totali_tu": 0,
            "punti_totali_bot": 0,
            "miglior_punteggio_tu": 0,
            "miglior_punteggio_bot": 0,
            "miglior_vittoria_margine": 0,
            "peggior_sconfitta_margine": 0,

            "partite_per_difficolta": {},
            "vittorie_per_difficolta": {},
            "vittorie_per_briscola": {},
            "mani_totali_tu": 0,
            "mani_totali_bot": 0,
            "partite_debug": 0,
            "partite_senza_audio": 0,
            "trofei": {},

            "ultima_partita": None
        }

    def load_stats(self):
        default = self.get_default_stats()
        path = Path(STATS_FILE)

        if not path.exists():
            return default

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

        # Merge leggero, così se aggiungiamo nuove statistiche in futuro
        # non si rompe il file vecchio.
        for key, value in default.items():
            loaded.setdefault(key, value)

        return loaded

    def save_stats(self):
        try:
            Path(STATS_FILE).write_text(
                json.dumps(self.stats, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

    def record_stats(self, result_key):
        """
        result_key: 'vittoria', 'sconfitta' oppure 'pareggio'
        """

        if self.stats_recorded_for_current_game:
            return

        self.stats_recorded_for_current_game = True

        self.ensure_stats_schema()
        s = self.stats
        diff = self.livello.get()
        margin = self.punti_p - self.punti_b

        s["partite"] += 1
        s["punti_totali_tu"] += self.punti_p
        s["punti_totali_bot"] += self.punti_b
        s["mani_totali_tu"] += self.mani_p
        s["mani_totali_bot"] += self.mani_b

        if self.debug_bot.get():
            s["partite_debug"] += 1

        if not self.audio_enabled.get():
            s["partite_senza_audio"] += 1
        s["miglior_punteggio_tu"] = max(s["miglior_punteggio_tu"], self.punti_p)
        s["miglior_punteggio_bot"] = max(s["miglior_punteggio_bot"], self.punti_b)

        s["partite_per_difficolta"][diff] = s["partite_per_difficolta"].get(diff, 0) + 1

        if result_key == "vittoria":
            s["vittorie"] += 1
            s["vittorie_per_difficolta"][diff] = s["vittorie_per_difficolta"].get(diff, 0) + 1

            s["winstreak_attuale"] += 1
            s["winstreak_migliore"] = max(s["winstreak_migliore"], s["winstreak_attuale"])

            s["losestreak_attuale"] = 0
            s["miglior_vittoria_margine"] = max(s["miglior_vittoria_margine"], margin)

        elif result_key == "sconfitta":
            s["sconfitte"] += 1

            s["losestreak_attuale"] += 1
            s["losestreak_migliore"] = max(s["losestreak_migliore"], s["losestreak_attuale"])

            s["winstreak_attuale"] = 0
            s["peggior_sconfitta_margine"] = max(s["peggior_sconfitta_margine"], abs(margin))

        else:
            s["pareggi"] += 1
            s["winstreak_attuale"] = 0
            s["losestreak_attuale"] = 0

        s["ultima_partita"] = {
            "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "risultato": result_key,
            "difficolta": diff,
            "punti_tu": self.punti_p,
            "punti_bot": self.punti_b,
            "mani_tu": self.mani_p,
            "mani_bot": self.mani_b,
            "briscola": getattr(self, "seme_briscola", "")
        }

        self.trofei_sbloccati_ultima_partita = self.check_trophies(result_key)
        self.save_stats()

    def format_stats_text(self):
        s = self.stats
        partite = max(s["partite"], 1)
        winrate = (s["vittorie"] / partite) * 100
        media_tu = s["punti_totali_tu"] / partite
        media_bot = s["punti_totali_bot"] / partite

        righe = [
            "STATISTICHE PERSONALI",
            "",
            f"Partite giocate: {s['partite']}",
            f"Vittorie: {s['vittorie']}",
            f"Sconfitte: {s['sconfitte']}",
            f"Pareggi: {s['pareggi']}",
            f"Percentuale vittorie: {winrate:.1f}%",
            "",
            f"Winstreak attuale: {s['winstreak_attuale']}",
            f"Migliore winstreak: {s['winstreak_migliore']}",
            f"Loss streak attuale: {s['losestreak_attuale']}",
            f"Peggiore loss streak: {s['losestreak_migliore']}",
            "",
            f"Punti medi tuoi: {media_tu:.1f}",
            f"Punti medi bot: {media_bot:.1f}",
            f"Miglior punteggio tuo: {s['miglior_punteggio_tu']}",
            f"Miglior punteggio bot: {s['miglior_punteggio_bot']}",
            f"Vittoria più larga: +{s['miglior_vittoria_margine']}",
            f"Sconfitta peggiore: -{s['peggior_sconfitta_margine']}",
            f"Mani medie vinte da te: {s.get('mani_totali_tu', 0) / partite:.1f}",
            f"Mani medie vinte dal bot: {s.get('mani_totali_bot', 0) / partite:.1f}",
            f"Partite giocate in debug: {s.get('partite_debug', 0)}",
            "",
            "PER DIFFICOLTÀ"
        ]

        livelli = ["Facile", "Medio", "Difficile", "Avanzato", "Avanzato+", "Avanzato++"]

        for liv in livelli:
            giocate = s["partite_per_difficolta"].get(liv, 0)
            vinte = s["vittorie_per_difficolta"].get(liv, 0)
            wr = (vinte / giocate * 100) if giocate else 0
            righe.append(f"{liv}: {vinte}/{giocate} vinte ({wr:.1f}%)")

        righe.extend(["", "TROFEI"])
        defs = self.get_trophy_definitions()
        trofei = s.get("trofei", {})

        if not trofei:
            righe.append("Nessun trofeo ancora sbloccato.")
        else:
            for key, label in defs.items():
                if key in trofei:
                    righe.append(f"✓ {label} ({trofei[key]})")

        if s.get("ultima_partita"):
            u = s["ultima_partita"]
            righe.extend([
                "",
                "ULTIMA PARTITA",
                f"Data: {u.get('data', '')}",
                f"Risultato: {u.get('risultato', '')}",
                f"Difficoltà: {u.get('difficolta', '')}",
                f"Punti: Tu {u.get('punti_tu', 0)} | Bot {u.get('punti_bot', 0)}",
                f"Mani: Tu {u.get('mani_tu', 0)} | Bot {u.get('mani_bot', 0)}",
                f"Briscola: {str(u.get('briscola', '')).upper()}",
            ])

        return "\n".join(righe)

    def show_stats(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Statistiche")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        if self.app_icon:
            try:
                dialog.iconphoto(True, self.app_icon)
            except Exception:
                pass

        frame = ttk.Frame(dialog, padding=(14, 14, 14, 14))
        frame.pack(fill="both", expand=True)

        text = tk.Text(
            frame,
            width=52,
            height=28,
            wrap="word",
            font=("Consolas", 10)
        )
        text.pack(fill="both", expand=True)

        text.insert("1.0", self.format_stats_text())
        text.configure(state="disabled")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(12, 0))

        def azzera():
            if messagebox.askyesno("Azzera statistiche", "Vuoi davvero azzerare tutte le statistiche?"):
                self.stats = self.get_default_stats()
                self.save_stats()
                dialog.destroy()
                self.show_stats()

        ttk.Button(btn_frame, text="Azzera statistiche", command=azzera).pack(side="left")
        ttk.Button(btn_frame, text="Chiudi", command=dialog.destroy).pack(side="right")

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
        dialog.geometry(f"+{x}+{y}")

    def show_tutorial(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Tutorial - Come si gioca a Briscola")
        dialog.geometry("640x560")
        dialog.resizable(True, True)
        dialog.transient(self.root)

        if self.app_icon:
            try:
                dialog.iconphoto(True, self.app_icon)
            except Exception:
                pass

        frame = ttk.Frame(dialog, padding=(14, 14, 14, 14))
        frame.pack(fill="both", expand=True)

        text = tk.Text(
            frame,
            wrap="word",
            font=("Segoe UI", 10),
            padx=8,
            pady=8
        )
        text.pack(fill="both", expand=True)

        tutorial = """COME SI GIOCA A BRISCOLA

OBIETTIVO
Vince chi fa più punti. Nel mazzo ci sono 120 punti totali.
Sopra 60 punti vinci, sotto 60 perdi, a 60 è pareggio.

PUNTI DELLE CARTE
Asso = 11 punti
Tre = 10 punti
Re = 4 punti
Cavallo = 3 punti
Fante = 2 punti
Tutte le altre carte valgono 0 punti.

FORZA DELLE CARTE
Quando due carte sono dello stesso seme, vince quella più forte.
Ordine dalla più forte alla più debole:
Asso, Tre, Re, Cavallo, Fante, 7, 6, 5, 4, 2.

LA BRISCOLA
Il seme indicato come BRISCOLA batte gli altri semi.
Per esempio, se la briscola è DENARI, anche un 2 di denari può battere un asso di coppe.

COME SI GIOCA NEL PROGRAMMA
1. Scegli la difficoltà nella finestra iniziale.
2. Durante il tuo turno clicca con il mouse su una delle tue tre carte.
3. Il bot giocherà automaticamente.
4. Chi vince la mano prende entrambe le carte.
5. Chi vince la mano pesca per primo.
6. Quando il mazzo finisce, si giocano le ultime carte rimaste in mano.
7. Alla fine compare il riepilogo con i punti.

DOVE CLICCARE
- Clicca sulle tue carte in basso.
- Dal menu Gioco puoi iniziare una nuova partita o uscire.
- Dal menu Opzioni puoi attivare Debug bot per vedere le carte del bot.
- Dal menu Opzioni puoi attivare Modalità allenamento per avere suggerimenti sulle tue carte.
- Dal menu Opzioni puoi spegnere audio e animazioni o cambiare velocità.
- Dal menu Gioco puoi aprire lo storico delle mani della partita.
- Dal menu Statistiche puoi vedere vittorie, sconfitte, winstreak e trofei.

CONSIGLI BASE
- Non sprecare briscole alte su carte che valgono 0.
- Cerca di prendere assi e tre: sono i carichi.
- Se giochi una carta di un seme normale, l'avversario può batterla con una briscola.
- Verso fine partita conta molto ricordare quali briscole sono già uscite.

MODALITÀ DEBUG
Se attivi Debug bot, le carte del bot vengono mostrate scoperte.
Serve per controllare se il bot sta giocando bene o se sta facendo scelte discutibili.
"""

        text.insert("1.0", tutorial)
        text.configure(state="disabled")

        ttk.Button(frame, text="Chiudi", command=dialog.destroy).pack(anchor="e", pady=(10, 0))

    # ========================================================
    # IMPOSTAZIONI, ASSET, TROFEI E FINESTRE EXTRA
    # ========================================================

    def get_default_settings(self):
        return {
            "difficolta": "Medio",
            "debug_bot": False,
            "audio_enabled": True,
            "animazioni_enabled": True,
            "training_mode": False,
            "velocita_animazioni": "Normale"
        }

    def load_settings(self):
        default = self.get_default_settings()
        path = Path(SETTINGS_FILE)

        if not path.exists():
            return default

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

        for key, value in default.items():
            loaded.setdefault(key, value)

        if loaded.get("velocita_animazioni") not in ["Lenta", "Normale", "Veloce"]:
            loaded["velocita_animazioni"] = "Normale"

        if loaded.get("difficolta") not in ["Facile", "Medio", "Difficile", "Avanzato", "Avanzato+", "Avanzato++"]:
            loaded["difficolta"] = "Medio"

        return loaded

    def save_settings(self):
        self.settings = {
            "difficolta": self.livello.get(),
            "debug_bot": self.debug_bot.get(),
            "audio_enabled": self.audio_enabled.get(),
            "animazioni_enabled": self.animazioni_enabled.get(),
            "training_mode": self.training_mode.get(),
            "velocita_animazioni": self.velocita_animazioni.get()
        }

        try:
            Path(SETTINGS_FILE).write_text(
                json.dumps(self.settings, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

    def on_setting_changed(self):
        self.save_settings()
        self.training_tip = ""
        self.render()

    def validate_assets(self):
        missing = []

        required = [Path("carte/retro.png")]
        required.extend(Path(f"carte/{seme}_{nome}.png") for seme in SEMI for nome, _punti, _forza in VALORI)

        for path in required:
            if not path.exists():
                missing.append(str(path))

        if missing:
            preview = "\n".join(missing[:12])
            more = "" if len(missing) <= 12 else f"\n...e altri {len(missing) - 12} file."
            messagebox.showerror(
                "File mancanti",
                "Non posso avviare il gioco perché mancano questi file:\n\n"
                f"{preview}{more}\n\n"
                "Controlla che la cartella 'carte' sia accanto al file Python."
            )
            return False

        return True

    def get_animation_params(self):
        if self.velocita_animazioni.get() == "Lenta":
            return 18, 24

        if self.velocita_animazioni.get() == "Veloce":
            return 7, 10

        return 12, 18

    def after_delay(self, callback):
        # Anche con animazioni spente lasciamo un piccolo respiro:
        # altrimenti il bot gioca "teletrasportato" e viene il mal di mare.
        if not self.animazioni_enabled.get():
            self.root.after(420, callback)
            return

        delay = 650
        if self.velocita_animazioni.get() == "Lenta":
            delay = 900
        elif self.velocita_animazioni.get() == "Veloce":
            delay = 250

        self.root.after(delay, callback)

    def card_to_text(self, carta):
        if carta is None:
            return "-"
        return f"{carta.nome} di {carta.seme}"

    def get_trophy_definitions(self):
        return {
            "prima_vittoria": "Prima vittoria",
            "tre_di_fila": "Tre vittorie di fila",
            "cinque_di_fila": "Cinque vittorie di fila",
            "dieci_partite": "Dieci partite giocate",
            "dieci_vittorie": "Dieci vittorie totali",
            "vittoria_difficile": "Vittoria a Difficile",
            "vittoria_avanzato_pp": "Vittoria ad Avanzato++",
            "ottanta_punti": "Vittoria con almeno 80 punti",
            "bot_sotto_40": "Vittoria lasciando il bot sotto 40 punti",
            "tutte_briscole": "Hai vinto almeno una volta con ogni seme di briscola"
        }

    def ensure_stats_schema(self):
        s = self.stats
        s.setdefault("trofei", {})
        s.setdefault("vittorie_per_briscola", {})
        s.setdefault("mani_totali_tu", 0)
        s.setdefault("mani_totali_bot", 0)
        s.setdefault("partite_senza_audio", 0)
        s.setdefault("partite_debug", 0)

    def unlock_trophy(self, key, unlocked_now):
        self.ensure_stats_schema()
        trofei = self.stats["trofei"]

        if key in trofei:
            return

        trofei[key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unlocked_now.append(self.get_trophy_definitions().get(key, key))

    def check_trophies(self, result_key):
        self.ensure_stats_schema()
        s = self.stats
        unlocked_now = []

        if s["partite"] >= 10:
            self.unlock_trophy("dieci_partite", unlocked_now)

        if result_key == "vittoria":
            self.unlock_trophy("prima_vittoria", unlocked_now)

            if s["winstreak_attuale"] >= 3:
                self.unlock_trophy("tre_di_fila", unlocked_now)

            if s["winstreak_attuale"] >= 5:
                self.unlock_trophy("cinque_di_fila", unlocked_now)

            if s["vittorie"] >= 10:
                self.unlock_trophy("dieci_vittorie", unlocked_now)

            if self.livello.get() == "Difficile":
                self.unlock_trophy("vittoria_difficile", unlocked_now)

            if self.livello.get() == "Avanzato++":
                self.unlock_trophy("vittoria_avanzato_pp", unlocked_now)

            if self.punti_p >= 80:
                self.unlock_trophy("ottanta_punti", unlocked_now)

            if self.punti_b <= 40:
                self.unlock_trophy("bot_sotto_40", unlocked_now)

            if hasattr(self, "seme_briscola"):
                s["vittorie_per_briscola"][self.seme_briscola] = s["vittorie_per_briscola"].get(self.seme_briscola, 0) + 1

            if all(seme in s["vittorie_per_briscola"] for seme in SEMI):
                self.unlock_trophy("tutte_briscole", unlocked_now)

        return unlocked_now

    def show_history(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Storico mani")
        dialog.geometry("620x520")
        dialog.transient(self.root)

        if self.app_icon:
            try:
                dialog.iconphoto(True, self.app_icon)
            except Exception:
                pass

        frame = ttk.Frame(dialog, padding=(14, 14, 14, 14))
        frame.pack(fill="both", expand=True)

        text = tk.Text(frame, wrap="word", font=("Consolas", 10), padx=8, pady=8)
        text.pack(fill="both", expand=True)

        if not self.storico_mani:
            text.insert("1.0", "Non ci sono ancora mani nello storico di questa partita.")
        else:
            righe = []
            for mano in self.storico_mani:
                righe.extend([
                    f"MANO {mano['numero']}",
                    f"Apre: {mano['apre']}",
                    f"Tu: {mano['player']}",
                    f"Bot: {mano['bot']}",
                    f"Vince: {mano['vincitore']}",
                    f"Punti mano: {mano['punti']}",
                    f"Parziale: Tu {mano['punti_tu']} | Bot {mano['punti_bot']}",
                ])

                if mano.get("motivo_bot"):
                    righe.append(f"Motivo bot: {mano['motivo_bot']}")

                righe.append("")

            text.insert("1.0", "\n".join(righe))

        text.configure(state="disabled")
        ttk.Button(frame, text="Chiudi", command=dialog.destroy).pack(anchor="e", pady=(10, 0))

    def explain_bot_choice(self, scelta):
        if scelta is None:
            return "Nessuna carta scelta."

        if self.c_p is None:
            if scelta.seme == self.seme_briscola:
                if scelta.punti == 0:
                    return "Apro con una briscola liscia: mano scomoda, provo a non regalare carichi."
                return "Apro con una briscola perché non ho scarti migliori."

            if scelta.punti == 0:
                return "Apro basso con una carta liscia non briscola."

            if scelta.punti < 10:
                return "Apro con una figura non briscola, senza rischiare un carico."

            return "Apro con un carico perché sembra abbastanza sicuro o non ho alternative migliori."

        winner = self.get_winner_logic(self.c_p, scelta)

        if winner == "bot":
            if self.c_p.punti >= 10:
                if scelta.seme == self.seme_briscola and self.c_p.seme != self.seme_briscola:
                    return "Prendo il carico usando la briscola più conveniente."
                return "Prendo il carico con una carta vincente."

            if scelta.seme == self.seme_briscola and self.c_p.seme != self.seme_briscola:
                return "Uso una briscola per prendere la mano."

            if scelta.punti >= 10:
                return "Prendo la mano ma sto usando un carico: scelta un po' rischiosa."

            return "Prendo la mano senza sprecare carte pesanti."

        if scelta.punti == 0:
            return "Non posso o non voglio prendere: scarto una liscia."

        if scelta.seme == self.seme_briscola:
            return "Non prendo: scarico una briscola poco utile in questa situazione."

        return "Non prendo: scarico la carta meno dannosa."

    def get_training_tip(self, idx):
        if idx < 0 or idx >= len(self.player):
            return ""

        carta = self.player[idx]

        if self.lock or not self.turn_player:
            return "Aspetta il tuo turno."

        if self.c_b is None:
            if carta.seme == self.seme_briscola and carta.punti >= 10:
                return "Carta forte: evita di aprire con un carico di briscola se non serve."
            if carta.punti == 0 and carta.seme != self.seme_briscola:
                return "Buona apertura prudente: carta liscia non briscola."
            if 0 < carta.punti < 10 and carta.seme != self.seme_briscola:
                return "Apertura accettabile: figura non briscola."
            if carta.punti >= 10 and carta.seme != self.seme_briscola:
                return "Attenzione: stai aprendo con un carico, il bot potrebbe prenderlo."
            if carta.seme == self.seme_briscola:
                return "Aprire con briscola può essere costoso: fallo solo se la mano è brutta."
            return "Scelta neutra."

        winner = self.get_winner_logic(carta, self.c_b)
        punti_tavolo = self.c_b.punti + carta.punti

        if winner == "player":
            if self.c_b.punti >= 10:
                return "Buona scelta: prendi un carico."
            if carta.seme == self.seme_briscola and self.c_b.punti == 0:
                return "Prendi con briscola una carta da 0: forse è uno spreco."
            return f"Prendi la mano da {punti_tavolo} punti."

        if carta.punti == 0:
            return "Scarto prudente: perdi la mano senza regalare punti."

        return "Attenzione: probabilmente perdi la mano regalando punti."

    def show_training_tip(self, idx):
        if not self.training_mode.get():
            return

        self.training_tip = self.get_training_tip(idx)
        self.render()

    def clear_training_tip(self):
        if not self.training_mode.get():
            return

        self.training_tip = ""
        self.render()

    # ========================================================
    # AUDIO
    # ========================================================

    def init_audio(self):
        self.snd_gioca = None
        self.snd_pesca = None

        if pygame is None:
            return

        try:
            pygame.mixer.init()
            self.snd_gioca = pygame.mixer.Sound("suoni/gioca.wav")
            self.snd_pesca = pygame.mixer.Sound("suoni/pesca.wav")
        except Exception:
            print("Audio non caricato. Verifica la cartella 'suoni'.")

    def play_sound(self, sound):
        if sound and self.audio_enabled.get():
            sound.play()

    # ========================================================
    # MENU
    # ========================================================

    def setup_menu(self):
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)

        self.menu_gioco = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Gioco", menu=self.menu_gioco)
        self.menu_gioco.add_command(label="Nuova Partita", command=self.reset_game)
        self.menu_gioco.add_command(label="Storico mani", command=self.show_history)
        self.menu_gioco.add_separator()
        self.menu_gioco.add_command(label="Esci", command=self.exit_game)

        self.menu_difficolta = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Difficoltà", menu=self.menu_difficolta)

        for liv in ["Facile", "Medio", "Difficile", "Avanzato", "Avanzato+", "Avanzato++"]:
            self.menu_difficolta.add_radiobutton(
                label=liv,
                variable=self.livello,
                value=liv,
                command=lambda l=liv: self.cambia_difficolta(l)
            )

        self.menu_opzioni = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Opzioni", menu=self.menu_opzioni)
        self.menu_opzioni.add_checkbutton(
            label="Debug bot: mostra carte",
            variable=self.debug_bot,
            command=self.on_setting_changed
        )
        self.menu_opzioni.add_checkbutton(
            label="Modalità allenamento",
            variable=self.training_mode,
            command=self.on_setting_changed
        )
        self.menu_opzioni.add_separator()
        self.menu_opzioni.add_checkbutton(
            label="Audio ON/OFF",
            variable=self.audio_enabled,
            command=self.on_setting_changed
        )
        self.menu_opzioni.add_checkbutton(
            label="Animazioni ON/OFF",
            variable=self.animazioni_enabled,
            command=self.on_setting_changed
        )
        self.menu_opzioni.add_separator()

        self.menu_velocita = tk.Menu(self.menu_opzioni, tearoff=0)
        self.menu_opzioni.add_cascade(label="Velocità animazioni", menu=self.menu_velocita)

        for vel in ["Lenta", "Normale", "Veloce"]:
            self.menu_velocita.add_radiobutton(
                label=vel,
                variable=self.velocita_animazioni,
                value=vel,
                command=self.on_setting_changed
            )

        self.menu_statistiche = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Statistiche", menu=self.menu_statistiche)
        self.menu_statistiche.add_command(label="Mostra statistiche", command=self.show_stats)

        self.menu_aiuto = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Aiuto", menu=self.menu_aiuto)
        self.menu_aiuto.add_command(label="Tutorial", command=self.show_tutorial)

    # ========================================================
    # UTILITY GRAFICHE
    # ========================================================

    def rounded_rect(self, x1, y1, x2, y2, r=24, **kwargs):
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]

        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def draw_text(self, x, y, text, size=14, color=WHITE, weight="normal", anchor="center"):
        return self.canvas.create_text(
            x,
            y,
            text=text,
            fill=color,
            font=("Segoe UI", size, weight),
            anchor=anchor
        )

    def draw_card(self, x, y, img, tag=None, outline=None):
        tags = tag if tag else ""

        # Ombra semplice e stabile: niente stipple/rounded polygon sui bordi delle carte.
        self.canvas.create_rectangle(
            x + 5,
            y + 7,
            x + CARD_W + 5,
            y + CARD_H + 7,
            fill="#02130a",
            outline="",
            tags=tags
        )

        # Bordo semplice rettangolare: molto più pulito sul Canvas di Tkinter.
        if outline:
            self.canvas.create_rectangle(
                x - 4,
                y - 4,
                x + CARD_W + 4,
                y + CARD_H + 4,
                outline=outline,
                width=3,
                tags=tags
            )

        return self.canvas.create_image(
            x,
            y,
            image=img,
            anchor="nw",
            tags=tags
        )

    def draw_empty_slot(self, x, y, label="", active=False):
        color = GOLD if active else TABLE_LIGHT

        self.canvas.create_rectangle(
            x,
            y,
            x + CARD_W,
            y + CARD_H,
            fill=TABLE_DARK,
            outline=color,
            width=2
        )

        if label:
            self.draw_text(
                x + CARD_W / 2,
                y + CARD_H / 2,
                label,
                size=10,
                color=MUTED,
                weight="bold"
            )

    # ========================================================
    # RENDER PRINCIPALE
    # ========================================================

    def render(self):
        self.canvas.delete("all")

        real_w = self.canvas.winfo_width()
        real_h = self.canvas.winfo_height()

        w = real_w if real_w > 100 else 1300
        h = real_h if real_h > 100 else 720

        cx = w / 2

        # Sfondo
        self.canvas.create_rectangle(0, 0, w, h, fill=BG, outline="")

        # Tavolo
        self.rounded_rect(
            45,
            24,
            w - 45,
            h - 24,
            r=50,
            fill=TABLE,
            outline="#0f9d4e",
            width=5
        )

        # Coordinate principali
        # Geometria simmetrica:
        # distanza carte bot -> box centrale = distanza box centrale -> tue carte.
        player_y = h - CARD_H - 48
        gap_between_hand_and_box = 34
        box_pad_y = 18

        played_y = player_y - gap_between_hand_and_box - CARD_H - box_pad_y
        bot_y = played_y - box_pad_y - gap_between_hand_and_box - CARD_H

        # Evita che le carte del bot escano troppo in alto nei monitor bassi.
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

        right_panel_x = w - 285

        self.pos["deck"] = (deck_x, deck_y)
        self.pos["bot_draw_target"] = (cx - CARD_W / 2, bot_y)
        self.pos["player_draw_target"] = (cx - CARD_W / 2, player_y)
        self.pos["played_bot"] = (played_bot_x, played_y)
        self.pos["played_player"] = (played_player_x, played_y)
        self.pos["bot_pile"] = (right_panel_x + 156, 105 + 28)
        self.pos["player_pile"] = (right_panel_x + 156, h - 165 + 28)

        # Area centrale delle carte giocate: più stretta e con margine vero.
        center_x1 = played_bot_x - 24
        center_y1 = played_y - box_pad_y
        center_x2 = played_player_x + CARD_W + 24
        center_y2 = played_y + CARD_H + box_pad_y

        self.rounded_rect(
            center_x1,
            center_y1,
            center_x2,
            center_y2,
            r=26,
            fill=TABLE_DARK,
            outline=TABLE_LIGHT,
            width=2
        )

        # Pannello mazzo / briscola
        panel_x1 = 75
        panel_y1 = deck_y - 52
        panel_x2 = briscola_x + CARD_W + 35
        panel_y2 = deck_y + CARD_H + 55

        self.rounded_rect(
            panel_x1,
            panel_y1,
            panel_x2,
            panel_y2,
            r=24,
            fill=BLACKISH,
            outline="#1ca956",
            width=2
        )

        # Scritte sopra le carte, centrate
        self.draw_text(
            deck_x + CARD_W / 2,
            deck_y - 29,
            "MAZZO",
            size=11,
            color=GOLD,
            weight="bold"
        )

        self.draw_text(
            briscola_x + CARD_W / 2,
            briscola_y - 29,
            "BRISCOLA",
            size=11,
            color=GOLD,
            weight="bold"
        )

        # Mazzo
        if hasattr(self, "deck"):
            carte_rimanenti = len(self.deck.carte) + (1 if self.briscola_fisica else 0)
            self.draw_text(
                deck_x + CARD_W / 2,
                deck_y + CARD_H + 26,
                f"{carte_rimanenti} carte",
                size=10,
                color=WHITE,
                weight="bold"
            )

        if hasattr(self, "deck") and self.deck.carte:
            self.draw_card(deck_x, deck_y, self.back_img, outline=TABLE_LIGHT)
        else:
            self.draw_empty_slot(deck_x, deck_y, "VUOTO")

        # Briscola
        if hasattr(self, "briscola_fisica") and self.briscola_fisica:
            self.draw_card(briscola_x, briscola_y, self.briscola_fisica.img, outline=TABLE_LIGHT)

            self.draw_text(
                briscola_x + CARD_W / 2,
                briscola_y + CARD_H + 26,
                self.seme_briscola.upper(),
                size=11,
                color=GOLD,
                weight="bold"
            )
        else:
            # La carta fisica della briscola è stata pescata,
            # ma lasciamo visibile il seme di briscola come promemoria.
            self.draw_empty_slot(briscola_x, briscola_y, "")

            if hasattr(self, "seme_briscola"):
                self.draw_text(
                    briscola_x + CARD_W / 2,
                    briscola_y + CARD_H + 26,
                    self.seme_briscola.upper(),
                    size=11,
                    color=GOLD,
                    weight="bold"
                )

        # Pannelli laterali senza punti
        self.draw_score_panel(
            right_panel_x,
            105,
            "BOT",
            getattr(self, "mani_b", 0)
        )

        self.draw_score_panel(
            right_panel_x,
            h - 165,
            "TU",
            getattr(self, "mani_p", 0)
        )

        # Difficoltà
        self.rounded_rect(
            75,
            h - 86,
            385,
            h - 45,
            r=17,
            fill=BLACKISH,
            outline="#1ca956",
            width=2
        )

        self.draw_text(
            230,
            h - 65,
            f"Difficoltà: {self.livello.get()}",
            size=11,
            color=GOLD,
            weight="bold"
        )

        # Messaggi leggeri per debug/allenamento.
        # La spiegazione del bot sta subito sotto le carte del bot,
        # così non finisce nascosta dalle carte o dai pannelli bassi.
        if self.debug_bot.get() and getattr(self, "bot_reason", ""):
            reason = f"Bot: {self.bot_reason}"

            if len(reason) > 92:
                reason = reason[:89] + "..."

            msg_w = 620
            msg_h = 30
            msg_y = bot_y + CARD_H + 17

            # Se per qualche motivo siamo troppo vicini allo slot centrale,
            # stringiamo un po' ma non sovrapponiamo.
            max_msg_y = center_y1 - 18
            msg_y = min(msg_y, max_msg_y)

            self.rounded_rect(
                cx - msg_w / 2,
                msg_y - msg_h / 2,
                cx + msg_w / 2,
                msg_y + msg_h / 2,
                r=12,
                fill=BLACKISH,
                outline=TABLE_LIGHT,
                width=1
            )

            self.canvas.create_text(
                cx,
                msg_y,
                text=reason,
                fill=MUTED,
                font=("Segoe UI", 9, "bold"),
                width=msg_w - 24,
                anchor="center"
            )

        if self.training_mode.get() and getattr(self, "training_tip", ""):
            self.rounded_rect(
                cx - 270,
                h - 116,
                cx + 270,
                h - 82,
                r=14,
                fill=BLACKISH,
                outline=GOLD,
                width=1
            )
            self.draw_text(
                cx,
                h - 99,
                self.training_tip,
                size=10,
                color=WHITE,
                weight="bold"
            )

        # Slot carte giocate
        self.draw_empty_slot(
            played_bot_x,
            played_y,
            "BOT",
            active=False
        )

        self.draw_empty_slot(
            played_player_x,
            played_y,
            "TU",
            active=False
        )

        if getattr(self, "c_b", None):
            self.draw_card(
                played_bot_x,
                played_y,
                self.c_b.img,
                tag="played",
                outline=GOLD
            )

        if getattr(self, "c_p", None):
            self.draw_card(
                played_player_x,
                played_y,
                self.c_p.img,
                tag="played",
                outline=GOLD
            )

        # Mani
        if hasattr(self, "bot"):
            self.draw_hand(self.bot, cx, bot_y, owner="bot")

        if hasattr(self, "player"):
            self.draw_hand(self.player, cx, player_y, owner="player")

    def draw_score_panel(self, x, y, title, mani):
        self.rounded_rect(
            x,
            y,
            x + 205,
            y + 105,
            r=22,
            fill=BLACKISH,
            outline=GOLD,
            width=2
        )

        self.draw_text(
            x + 102,
            y + 28,
            title,
            size=17,
            color=GOLD,
            weight="bold"
        )

        # Prima mano non ancora vinta: box pulito, solo testo.
        if mani <= 0:
            self.draw_text(
                x + 102,
                y + 70,
                "Mani vinte: 0",
                size=12,
                color=WHITE,
                weight="bold"
            )
            return

        # Dopo la prima mano vinta, mostriamo anche il dorso nel box.
        self.draw_text(
            x + 75,
            y + 68,
            f"Mani vinte: {mani}",
            size=12,
            color=WHITE,
            weight="bold"
        )

        # Dorsino a destra del testo.
        self.canvas.create_image(
            x + 156,
            y + 28,
            image=self.back_small,
            anchor="nw"
        )

    def draw_hand(self, cards, cx, y, owner):
        if not cards:
            return

        gap = 16
        total_w = len(cards) * CARD_W + (len(cards) - 1) * gap
        start_x = cx - total_w / 2

        for i, c in enumerate(cards):
            x = start_x + i * (CARD_W + gap)
            self.pos[f"{owner}_card_{i}"] = (x, y)

            if owner == "player":
                tag = f"player_card_{i}"

                outline = GOLD if getattr(self, "turn_player", True) and not getattr(self, "lock", False) else TABLE_LIGHT

                self.draw_card(
                    x,
                    y,
                    c.img,
                    tag=tag,
                    outline=outline
                )

                self.canvas.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda event, idx=i: self.on_move(idx)
                )

                self.canvas.tag_bind(
                    tag,
                    "<Enter>",
                    lambda event, idx=i: [self.canvas.config(cursor="hand2"), self.show_training_tip(idx)]
                )

                self.canvas.tag_bind(
                    tag,
                    "<Leave>",
                    lambda event: [self.canvas.config(cursor=""), self.clear_training_tip()]
                )

            else:
                # Debug OFF: bot coperto.
                # Debug ON: bot scoperto, utile per controllare la logica.
                img = c.img if self.debug_bot.get() else self.back_img

                self.draw_card(
                    x,
                    y,
                    img,
                    outline=TABLE_LIGHT
                )

    # ========================================================
    # PARTITA
    # ========================================================

    def start_game(self):
        self.deck = Mazzo()

        self.player = [self.deck.pesca() for _ in range(3)]
        self.bot = [self.deck.pesca() for _ in range(3)]

        self.briscola_fisica = self.deck.carte.pop()
        self.seme_briscola = self.briscola_fisica.seme

        self.punti_p = 0
        self.punti_b = 0

        self.mani_p = 0
        self.mani_b = 0

        self.c_p = None
        self.c_b = None

        self.lock = False
        self.animating_card_play = False
        self.turn_player = True
        self.chi_inizia = "player"

        self.carte_uscite = []
        self.storico_mani = []
        self.bot_reason = ""
        self.training_tip = ""
        self.stats_recorded_for_current_game = False

        self.livello_attivo = self.livello.get()
        self.save_settings()

        self.render()

    def reset_game(self, event=None):
        if messagebox.askyesno("Nuova partita", "Vuoi ricominciare?"):
            self.reset_game_automatico()

    def reset_game_automatico(self):
        self.start_game()

    def exit_game(self, event=None):
        if messagebox.askyesno("Esci", "Vuoi uscire dal gioco?"):
            self.root.destroy()

    def cambia_difficolta(self, nuovo_livello):
        if messagebox.askyesno(
            "Cambia difficoltà",
            "Per cambiare difficoltà devi ricominciare la partita. Continuare?"
        ):
            self.livello.set(nuovo_livello)
            self.livello_attivo = nuovo_livello
            self.save_settings()
            self.reset_game_automatico()
        else:
            self.livello.set(self.livello_attivo)
            self.render()

    def scelta_difficolta_iniziale(self):
        """
        Finestra iniziale in stile più vicino a una vera finestra di sistema Windows.
        Usa ttk, quindi su Windows prende il tema nativo disponibile.
        """

        dialog = tk.Toplevel(self.root)
        dialog.title("Scegli difficoltà")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        if self.app_icon:
            try:
                dialog.iconphoto(True, self.app_icon)
            except Exception:
                pass

        # Prova a usare il tema Windows nativo, quando disponibile.
        style = ttk.Style(dialog)

        for theme_name in ("vista", "xpnative", "winnative"):
            if theme_name in style.theme_names():
                try:
                    style.theme_use(theme_name)
                    break
                except Exception:
                    pass

        selected = tk.StringVar(value=self.livello.get() or "Medio")

        main = ttk.Frame(dialog, padding=(18, 16, 18, 14))
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Scegli la difficoltà della partita",
            font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(
            main,
            text="Scegli il livello con cui vuoi iniziare la partita.",
            font=("Segoe UI", 9)
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        radio_frame = ttk.LabelFrame(main, text="Difficoltà", padding=(12, 8, 12, 8))
        radio_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        # Colonna sinistra: livelli normali.
        # Colonna destra: livelli avanzati.
        livelli_sinistra = ["Facile", "Medio", "Difficile"]
        livelli_destra = ["Avanzato", "Avanzato+", "Avanzato++"]

        ttk.Label(
            radio_frame,
            text="Normale",
            font=("Segoe UI", 9, "bold")
        ).grid(row=0, column=0, sticky="w", padx=(0, 34), pady=(0, 5))

        ttk.Label(
            radio_frame,
            text="Avanzato",
            font=("Segoe UI", 9, "bold")
        ).grid(row=0, column=1, sticky="w", pady=(0, 5))

        for i, liv in enumerate(livelli_sinistra, start=1):
            ttk.Radiobutton(
                radio_frame,
                text=liv,
                variable=selected,
                value=liv
            ).grid(row=i, column=0, sticky="w", padx=(0, 34), pady=3)

        for i, liv in enumerate(livelli_destra, start=1):
            ttk.Radiobutton(
                radio_frame,
                text=liv,
                variable=selected,
                value=liv
            ).grid(row=i, column=1, sticky="w", pady=3)

        button_frame = ttk.Frame(main)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="e")

        def conferma():
            liv = selected.get()
            self.livello.set(liv)
            self.livello_attivo = liv
            self.save_settings()
            dialog.destroy()

        def esci_senza_giocare():
            self.app_should_close = True
            dialog.destroy()
            self.root.destroy()

        ok_btn = ttk.Button(
            button_frame,
            text="OK",
            command=conferma,
            width=12
        )
        ok_btn.pack(side="right", padx=(8, 0))

        cancel_btn = ttk.Button(
            button_frame,
            text="Esci",
            command=esci_senza_giocare,
            width=12
        )
        cancel_btn.pack(side="right")

        dialog.protocol("WM_DELETE_WINDOW", esci_senza_giocare)
        dialog.bind("<Return>", lambda event: conferma())
        dialog.bind("<Escape>", lambda event: esci_senza_giocare())

        dialog.update_idletasks()

        # Centra la finestra rispetto allo schermo.
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        ok_btn.focus_set()
        self.root.wait_window(dialog)

    # ========================================================
    # MOSSE
    # ========================================================

    def animate_play_card(self, carta, src, dst, callback):
        """
        Animazione carta giocata: dalla mano allo slot centrale.
        """
        if carta is None:
            callback()
            return

        if not self.animazioni_enabled.get():
            self.root.after(120, callback)
            return

        sx, sy = src
        dx, dy = dst

        self.animating_card_play = True
        anim_id = self.canvas.create_image(sx, sy, image=carta.img, anchor="nw", tags="anim_play")

        if self.velocita_animazioni.get() == "Lenta":
            steps = 18
            step_delay = 24
        elif self.velocita_animazioni.get() == "Veloce":
            steps = 10
            step_delay = 12
        else:
            steps = 14
            step_delay = 18

        def step(n):
            if n >= steps:
                self.canvas.delete(anim_id)
                self.animating_card_play = False
                callback()
                return

            self.canvas.move(anim_id, (dx - sx) / steps, (dy - sy) / steps)
            self.root.after(step_delay, lambda: step(n + 1))

        step(0)

    def on_move(self, i):
        if self.lock or self.animating_card_play:
            return

        if not self.turn_player:
            return

        if self.c_p:
            return

        if i < 0 or i >= len(self.player):
            return

        self.play_sound(self.snd_gioca)
        self.training_tip = ""

        carta = self.player[i]
        src = self.pos.get(f"player_card_{i}", self.pos.get("player_draw_target", (500, 470)))
        dst = self.pos.get("played_player", src)

        # Tolgo subito la carta dalla mano, così durante l'animazione non rimane duplicata.
        self.player.pop(i)
        self.turn_player = False
        self.render()

        def after_card_reaches_table():
            self.c_p = carta

            if self.c_b is None:
                self.chi_inizia = "player"
                self.render()
                self.after_delay(self.bot_move)
            else:
                self.render()
                self.after_delay(self.resolve)

        self.animate_play_card(carta, src, dst, after_card_reaches_table)

    def bot_move(self):
        if self.lock or self.animating_card_play:
            return

        self.bot = [c for c in self.bot if c is not None]

        if not self.bot:
            return

        if self.c_p is None:
            self.chi_inizia = "bot"

        diff = self.livello.get()

        if diff == "Facile":
            scelta = self.logic_facile()

        elif diff in ["Difficile", "Avanzato", "Avanzato+", "Avanzato++"]:
            scelta = self.logic_difficile()

        else:
            scelta = self.logic_medio()

        if scelta is None:
            scelta = random.choice(self.bot)

        idx = self.bot.index(scelta)
        src = self.pos.get(f"bot_card_{idx}", self.pos.get("bot_draw_target", (500, 82)))
        dst = self.pos.get("played_bot", src)

        self.bot_reason = self.explain_bot_choice(scelta)

        # Tolgo subito la carta dalla mano del bot, poi la animo verso il tavolo.
        self.bot.remove(scelta)

        self.play_sound(self.snd_gioca)
        self.render()

        def after_card_reaches_table():
            self.c_b = scelta

            if self.c_p:
                self.render()
                self.after_delay(self.resolve)
            else:
                self.turn_player = True
                self.render()

        self.animate_play_card(scelta, src, dst, after_card_reaches_table)

    # ========================================================
    # LOGICA BOT
    # ========================================================

    def logic_facile(self):
        return min(
            self.bot,
            key=lambda c: (c.seme == self.seme_briscola, c.forza)
        )

    def logic_medio(self):
        mano = [c for c in self.bot if c is not None]

        if not mano:
            return None

        briscola = self.seme_briscola
        mazzo_vuoto = len(self.deck.carte) == 0
        fine_partita = len(self.deck.carte) < 6

        uscite = getattr(self, "carte_uscite", [])
        briscole_uscite = sum(1 for c in uscite if c is not None and c.seme == briscola)
        briscole_in_mano_bot = len([c for c in mano if c.seme == briscola])
        briscole_in_giro = 10 - briscole_uscite - briscole_in_mano_bot
        rischio_briscola_alto = briscole_in_giro >= 3

        briscole = [c for c in mano if c.seme == briscola]
        non_briscole = [c for c in mano if c.seme != briscola]

        carichi_nb = [c for c in non_briscole if c.punti >= 10]
        lisce_nb = [c for c in non_briscole if c.punti == 0]
        figure_nb = [c for c in non_briscole if 0 < c.punti < 10]

        if self.c_p is None:
            self.chi_inizia = "bot"

            return self._apri(
                mano,
                briscole,
                non_briscole,
                carichi_nb,
                lisce_nb,
                figure_nb,
                briscola
            )

        punti_tavolo = self.c_p.punti

        vincenti_nb = [
            c for c in non_briscole
            if self.get_winner_logic(self.c_p, c) == "bot"
        ]

        vincenti_b = [
            c for c in briscole
            if self.get_winner_logic(self.c_p, c) == "bot"
        ]

        if punti_tavolo >= 10:
            if vincenti_nb:
                return max(vincenti_nb, key=lambda c: (c.punti, c.forza))

            if vincenti_b:
                return min(vincenti_b, key=lambda c: (c.punti, c.forza))

            return self._scarta_piu_bassa(mano, briscole, non_briscole)

        if vincenti_nb:
            if punti_tavolo == 0 and not mazzo_vuoto and not fine_partita and rischio_briscola_alto:
                non_carichi_v = [c for c in vincenti_nb if c.punti < 10]

                if non_carichi_v:
                    return max(non_carichi_v, key=lambda c: (c.punti, c.forza))

                briscole_figure = [c for c in briscole if 0 < c.punti < 10]

                if briscole_figure:
                    return min(briscole_figure, key=lambda c: (c.punti, c.forza))

            non_carichi_v = [c for c in vincenti_nb if c.punti < 10]

            if non_carichi_v:
                return max(non_carichi_v, key=lambda c: (c.punti, c.forza))

            return max(vincenti_nb, key=lambda c: (c.punti, c.forza))

        if lisce_nb:
            return min(lisce_nb, key=lambda c: c.forza)

        if len(carichi_nb) >= 2 and briscole:
            briscole_figure = [c for c in briscole if 0 < c.punti < 10]

            if briscole_figure:
                return min(briscole_figure, key=lambda c: (c.punti, c.forza))

        if carichi_nb and briscole:
            briscole_lisce = [c for c in briscole if c.punti == 0]

            if briscole_lisce:
                return min(briscole_lisce, key=lambda c: c.forza)

        return self._scarta_piu_bassa(mano, briscole, non_briscole)

    def logic_difficile(self):
        mano = [c for c in self.bot if c is not None]

        if not mano:
            return None

        briscola = self.seme_briscola
        mazzo_vuoto = len(self.deck.carte) == 0
        fine_partita = len(self.deck.carte) < 6

        briscole = [c for c in mano if c.seme == briscola]
        non_briscole = [c for c in mano if c.seme != briscola]

        carichi_nb = [c for c in non_briscole if c.punti >= 10]
        lisce_nb = [c for c in non_briscole if c.punti == 0]
        figure_nb = [c for c in non_briscole if 0 < c.punti < 10]

        uscite = set((c.seme, c.nome) for c in self.carte_uscite if c is not None)

        def e_uscita(seme, nome):
            return (seme, nome) in uscite

        briscole_uscite = sum(1 for s, n in uscite if s == briscola)
        briscole_in_mano_bot = len(briscole)
        briscole_in_giro = 10 - briscole_uscite - briscole_in_mano_bot

        rischio_briscola = briscole_in_giro > 0
        rischio_briscola_alto = briscole_in_giro >= 3

        punti_garantiti = 0

        for c in mano:
            if c.seme == briscola and c.punti >= 10:
                punti_garantiti += c.punti

            elif c.seme != briscola:
                if e_uscita(c.seme, "asso") and not rischio_briscola:
                    punti_garantiti += c.punti

        ha_gia_vinto = (self.punti_b + punti_garantiti) > 60

        if self.c_p is None:
            self.chi_inizia = "bot"

            if ha_gia_vinto:
                if lisce_nb:
                    return min(lisce_nb, key=lambda c: c.forza)

                if figure_nb:
                    return min(figure_nb, key=lambda c: c.forza)

                return self._apri(
                    mano,
                    briscole,
                    non_briscole,
                    carichi_nb,
                    lisce_nb,
                    figure_nb,
                    briscola
                )

            for c in sorted(carichi_nb, key=lambda c: c.punti, reverse=True):
                nessuno_lo_batte = (
                    c.nome == "asso" or
                    (c.nome == "3" and e_uscita(c.seme, "asso"))
                )

                if nessuno_lo_batte and not rischio_briscola_alto:
                    return c

            return self._apri(
                mano,
                briscole,
                non_briscole,
                carichi_nb,
                lisce_nb,
                figure_nb,
                briscola
            )

        punti_tavolo = self.c_p.punti

        vincenti_nb = [
            c for c in non_briscole
            if self.get_winner_logic(self.c_p, c) == "bot"
        ]

        vincenti_b = [
            c for c in briscole
            if self.get_winner_logic(self.c_p, c) == "bot"
        ]

        if punti_tavolo >= 10:
            if vincenti_nb:
                return max(vincenti_nb, key=lambda c: (c.punti, c.forza))

            if vincenti_b:
                return min(vincenti_b, key=lambda c: (c.punti, c.forza))

            return self._scarta_piu_bassa(mano, briscole, non_briscole)

        if vincenti_nb and not rischio_briscola:
            return max(vincenti_nb, key=lambda c: (c.punti, c.forza))

        if vincenti_nb:
            if punti_tavolo == 0 and not mazzo_vuoto and not fine_partita and rischio_briscola_alto:
                non_carichi_v = [c for c in vincenti_nb if c.punti < 10]

                if non_carichi_v:
                    return max(non_carichi_v, key=lambda c: (c.punti, c.forza))

                briscole_figure = [c for c in briscole if 0 < c.punti < 10]

                if briscole_figure:
                    return min(briscole_figure, key=lambda c: (c.punti, c.forza))

            non_carichi_v = [c for c in vincenti_nb if c.punti < 10]

            if non_carichi_v:
                return max(non_carichi_v, key=lambda c: (c.punti, c.forza))

            return max(vincenti_nb, key=lambda c: (c.punti, c.forza))

        if lisce_nb:
            return min(lisce_nb, key=lambda c: c.forza)

        if len(carichi_nb) >= 2 and briscole:
            briscole_figure = [c for c in briscole if 0 < c.punti < 10]

            if briscole_figure:
                return min(briscole_figure, key=lambda c: (c.punti, c.forza))

        if carichi_nb and briscole:
            briscole_lisce = [c for c in briscole if c.punti == 0]

            if briscole_lisce:
                return min(briscole_lisce, key=lambda c: c.forza)

        return self._scarta_piu_bassa(mano, briscole, non_briscole)

    # ========================================================
    # HELPER LOGICA
    # ========================================================

    def _apri(self, mano, briscole, non_briscole, carichi_nb, lisce_nb, figure_nb, briscola):
        if lisce_nb:
            return min(lisce_nb, key=lambda c: c.forza)

        if figure_nb:
            return min(figure_nb, key=lambda c: c.forza)

        if non_briscole and briscole:
            briscole_lisce = [c for c in briscole if c.punti == 0]

            if briscole_lisce:
                return min(briscole_lisce, key=lambda c: c.forza)

            briscole_figure = [c for c in briscole if 0 < c.punti < 10]

            if briscole_figure and all(c.punti >= 10 for c in non_briscole):
                return min(briscole_figure, key=lambda c: c.forza)

            return min(non_briscole, key=lambda c: (c.punti, c.forza))

        if briscole and not non_briscole:
            return min(briscole, key=lambda c: (c.punti, c.forza))

        return min(mano, key=lambda c: (c.seme == briscola, c.punti, c.forza))

    def _scarta_piu_bassa(self, mano, briscole, non_briscole):
        if non_briscole:
            return min(non_briscole, key=lambda c: (c.punti, c.forza))

        return min(briscole, key=lambda c: (c.punti, c.forza))

    # ========================================================
    # RISOLUZIONE MANO
    # ========================================================

    def get_winner_logic(self, cp, cb):
        if self.chi_inizia == "player":
            first = cp
            second = cb
            first_owner = "player"
            second_owner = "bot"
        else:
            first = cb
            second = cp
            first_owner = "bot"
            second_owner = "player"

        if first.seme == second.seme:
            winner = first if first.forza > second.forza else second

        elif second.seme == self.seme_briscola:
            winner = second

        elif first.seme == self.seme_briscola:
            winner = first

        else:
            winner = first

        return first_owner if winner == first else second_owner

    def resolve(self):
        self.lock = True

        vincitore = self.get_winner_logic(self.c_p, self.c_b)

        self.render()
        self.root.after(420, lambda: self.animate_to_side(vincitore))

    def animate_to_side(self, vincitore):
        if not self.animazioni_enabled.get():
            # Nessun movimento, ma pausa breve per far vedere le due carte sul tavolo.
            self.root.after(420, lambda: self.complete_turn(vincitore))
            return

        self.canvas.delete("played")

        real_w = self.canvas.winfo_width()
        real_h = self.canvas.winfo_height()

        w = real_w if real_w > 100 else 1300
        h = real_h if real_h > 100 else 720

        cx = w / 2

        player_y = h - CARD_H - 48
        gap_between_hand_and_box = 34
        box_pad_y = 18

        played_y = player_y - gap_between_hand_and_box - CARD_H - box_pad_y
        bot_y = played_y - box_pad_y - gap_between_hand_and_box - CARD_H

        if bot_y < 38:
            delta = 38 - bot_y
            bot_y += delta
            played_y += delta

        played_bot_x = cx - CARD_W - 20
        played_player_x = cx + 20

        right_panel_x = w - 285

        if vincitore == "player":
            tx, ty = self.pos.get("player_pile", (right_panel_x + 156, h - 165 + 28))
        else:
            tx, ty = self.pos.get("bot_pile", (right_panel_x + 156, 105 + 28))

        cp_a = self.canvas.create_image(
            played_player_x,
            played_y,
            image=self.c_p.img,
            anchor="nw"
        )

        cb_a = self.canvas.create_image(
            played_bot_x,
            played_y,
            image=self.c_b.img,
            anchor="nw"
        )

        steps, delay_ms = self.get_animation_params()

        def step(i):
            if i >= steps:
                self.canvas.delete(cp_a)
                self.canvas.delete(cb_a)
                self.complete_turn(vincitore)
                return

            self.canvas.move(cp_a, (tx - played_player_x) / steps, (ty - played_y) / steps)
            self.canvas.move(cb_a, (tx - played_bot_x) / steps, (ty - played_y) / steps)

            self.root.after(delay_ms, lambda: step(i + 1))

        step(0)

    def complete_turn(self, vincitore):
        # Salvo le carte giocate in variabili locali:
        # subito dopo le togliamo dagli slot centrali, così la pesca non parte
        # mentre le carte della mano precedente sono ancora visibili sul tavolo.
        carta_player = self.c_p
        carta_bot = self.c_b

        if carta_player:
            self.carte_uscite.append(carta_player)

        if carta_bot:
            self.carte_uscite.append(carta_bot)

        punti_mano = carta_player.punti + carta_bot.punti

        if vincitore == "player":
            self.punti_p += punti_mano
            self.mani_p += 1
        else:
            self.punti_b += punti_mano
            self.mani_b += 1

        self.storico_mani.append({
            "numero": len(self.storico_mani) + 1,
            "apre": "Tu" if self.chi_inizia == "player" else "Bot",
            "player": self.card_to_text(carta_player),
            "bot": self.card_to_text(carta_bot),
            "vincitore": "Tu" if vincitore == "player" else "Bot",
            "punti": punti_mano,
            "punti_tu": self.punti_p,
            "punti_bot": self.punti_b,
            "motivo_bot": self.bot_reason if self.debug_bot.get() else ""
        })

        p1_owner = vincitore
        p2_owner = "bot" if vincitore == "player" else "player"

        # Pulizia immediata degli slot centrali prima della pesca.
        # Questo vale soprattutto con animazioni OFF, ma rende più pulita anche
        # la sequenza con animazioni ON.
        self.c_p = None
        self.c_b = None
        self.render()

        if self.deck.carte:
            if p1_owner == "bot" and self.livello.get() in ["Avanzato", "Avanzato+", "Avanzato++"]:
                c1 = self.deck.pesca_truccata(self.livello.get(), self.seme_briscola, self.bot)
            else:
                c1 = self.deck.pesca()

            if self.deck.carte:
                if p2_owner == "bot" and self.livello.get() in ["Avanzato", "Avanzato+", "Avanzato++"]:
                    c2 = self.deck.pesca_truccata(self.livello.get(), self.seme_briscola, self.bot)
                else:
                    c2 = self.deck.pesca()
            else:
                c2 = self.briscola_fisica

            if c2 == self.briscola_fisica:
                self.briscola_fisica = None

            self.animate_draw(
                p1_owner,
                c1,
                lambda: self.after_first_draw(p1_owner, c1, p2_owner, c2, vincitore)
            )

        elif self.briscola_fisica:
            c1 = self.briscola_fisica
            self.briscola_fisica = None

            self.animate_draw(
                p1_owner,
                c1,
                lambda: self.after_last_briscola_draw(p1_owner, c1, vincitore)
            )

        else:
            self.finalize_turn(vincitore)

    def after_first_draw(self, p1_owner, c1, p2_owner, c2, vincitore):
        self.add_to_hand(p1_owner, c1)

        self.animate_draw(
            p2_owner,
            c2,
            lambda: self.after_second_draw(p2_owner, c2, vincitore)
        )

    def after_second_draw(self, p2_owner, c2, vincitore):
        self.add_to_hand(p2_owner, c2)
        self.finalize_turn(vincitore)

    def after_last_briscola_draw(self, p1_owner, c1, vincitore):
        self.add_to_hand(p1_owner, c1)
        self.finalize_turn(vincitore)

    def animate_draw(self, chi, carta_obj, callback):
        if carta_obj is None:
            callback()
            return

        if not self.animazioni_enabled.get():
            self.root.after(220, callback)
            return

        self.play_sound(self.snd_pesca)

        sx, sy = self.pos.get("deck", (110, 260))

        if chi == "player":
            dx, dy = self.pos.get("player_draw_target", (500, 470))
        else:
            dx, dy = self.pos.get("bot_draw_target", (500, 38))

        img = carta_obj.img if (chi == "player" or self.debug_bot.get()) else self.back_img

        card_id = self.canvas.create_image(sx, sy, image=img, anchor="nw")

        steps, delay_ms = self.get_animation_params()

        def step(i):
            if i >= steps:
                self.canvas.delete(card_id)
                callback()
                return

            self.canvas.move(card_id, (dx - sx) / steps, (dy - sy) / steps)
            self.root.after(delay_ms, lambda: step(i + 1))

        step(0)

    def add_to_hand(self, chi, carta):
        if carta is None:
            return

        if chi == "player":
            self.player.append(carta)
        else:
            self.bot.append(carta)

        self.render()

    def finalize_turn(self, vincitore):
        self.c_p = None
        self.c_b = None

        self.lock = False
        self.turn_player = vincitore == "player"

        self.render()

        if not self.player and not self.bot:
            self.end_game()
            return

        if not self.turn_player:
            self.after_delay(self.bot_move)

    def end_game(self):
        if self.punti_p > 60:
            res = "HAI VINTO!"
            result_key = "vittoria"
        elif self.punti_b > 60:
            res = "HAI PERSO!"
            result_key = "sconfitta"
        else:
            res = "PAREGGIO!"
            result_key = "pareggio"

        self.record_stats(result_key)
        self.show_final_summary(res)

    def show_final_summary(self, res):
        dialog = tk.Toplevel(self.root)
        dialog.title("Fine partita")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        if self.app_icon:
            try:
                dialog.iconphoto(True, self.app_icon)
            except Exception:
                pass

        main = ttk.Frame(dialog, padding=(22, 18, 22, 16))
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="FINE PARTITA",
            font=("Segoe UI", 16, "bold")
        ).grid(row=0, column=0, columnspan=2, pady=(0, 8))

        ttk.Label(
            main,
            text=res,
            font=("Segoe UI", 13, "bold")
        ).grid(row=1, column=0, columnspan=2, pady=(0, 16))

        rows = [
            ("Punti", f"Tu {self.punti_p} | Bot {self.punti_b}"),
            ("Mani vinte", f"Tu {self.mani_p} | Bot {self.mani_b}"),
            ("Briscola", str(getattr(self, "seme_briscola", "")).upper()),
            ("Difficoltà", self.livello.get()),
            ("Winstreak attuale", str(self.stats.get("winstreak_attuale", 0))),
            ("Migliore winstreak", str(self.stats.get("winstreak_migliore", 0))),
        ]

        for r, (label, value) in enumerate(rows, start=2):
            ttk.Label(main, text=label + ":", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", padx=(0, 16), pady=3)
            ttk.Label(main, text=value, font=("Segoe UI", 10)).grid(row=r, column=1, sticky="w", pady=3)

        next_row = 2 + len(rows)

        if self.trofei_sbloccati_ultima_partita:
            ttk.Label(
                main,
                text="Trofei sbloccati:",
                font=("Segoe UI", 10, "bold")
            ).grid(row=next_row, column=0, columnspan=2, sticky="w", pady=(14, 4))

            next_row += 1

            for trophy in self.trofei_sbloccati_ultima_partita:
                ttk.Label(
                    main,
                    text=f"✓ {trophy}",
                    font=("Segoe UI", 10)
                ).grid(row=next_row, column=0, columnspan=2, sticky="w", pady=2)
                next_row += 1

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=next_row, column=0, columnspan=2, sticky="e", pady=(18, 0))

        def nuova():
            dialog.destroy()
            self.reset_game_automatico()

        def statistiche():
            self.show_stats()

        def esci():
            dialog.destroy()
            self.root.destroy()

        ttk.Button(btn_frame, text="Nuova partita", command=nuova, width=15).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Statistiche", command=statistiche, width=13).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="Esci", command=esci, width=10).pack(side="right")

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
        dialog.geometry(f"+{x}+{y}")

        self.root.wait_window(dialog)


# ============================================================
# AVVIO
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    game = BriscolaGame(root)

    if not getattr(game, "app_should_close", False):
        root.mainloop()
