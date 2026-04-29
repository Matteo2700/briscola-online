import json
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from PIL import Image, ImageTk

ICON_FILES = ["icona.ico", "icon.ico", "icona.png", "icon.png"]
PROFILE_FILE = "briscola_profile.json"
BOT_STATS_FILE = "briscola_stats.json"

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


def load_icon(root):
    for icon_name in ICON_FILES:
        path = Path(icon_name)
        if not path.exists():
            continue

        try:
            if path.suffix.lower() == ".ico":
                root.iconbitmap(str(path))
                return None

            img = Image.open(path).resize((256, 256), RESAMPLE)
            icon = ImageTk.PhotoImage(img)
            root.iconphoto(True, icon)
            return icon
        except Exception:
            pass

    return None


def choose_bot_difficulty(root):
    dialog = tk.Toplevel(root)
    dialog.title("Scegli difficoltà")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    selected = tk.StringVar(value="Medio")
    result = {"value": None}

    frame = ttk.Frame(dialog, padding=(18, 16, 18, 14))
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="Scegli la difficoltà",
        font=("Segoe UI", 12, "bold")
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

    levels = ttk.LabelFrame(frame, text="Difficoltà bot", padding=(12, 8, 12, 8))
    levels.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 14))

    left = ["Facile", "Medio", "Difficile"]
    right = ["Avanzato", "Avanzato+", "Avanzato++"]

    ttk.Label(levels, text="Normale", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 34), pady=(0, 5))
    ttk.Label(levels, text="Avanzato", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", pady=(0, 5))

    for i, liv in enumerate(left, start=1):
        ttk.Radiobutton(levels, text=liv, variable=selected, value=liv).grid(row=i, column=0, sticky="w", padx=(0, 34), pady=3)

    for i, liv in enumerate(right, start=1):
        ttk.Radiobutton(levels, text=liv, variable=selected, value=liv).grid(row=i, column=1, sticky="w", pady=3)

    buttons = ttk.Frame(frame)
    buttons.grid(row=2, column=0, columnspan=2, sticky="e")

    def ok():
        result["value"] = selected.get()
        dialog.destroy()

    def back():
        result["value"] = None
        dialog.destroy()

    ok_btn = ttk.Button(buttons, text="OK", width=12, command=ok)
    ok_btn.pack(side="right", padx=(8, 0))
    ttk.Button(buttons, text="Indietro", width=12, command=back).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", back)
    dialog.bind("<Return>", lambda event: ok())
    dialog.bind("<Escape>", lambda event: back())

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
    dialog.geometry(f"+{x}+{y}")

    ok_btn.focus_set()
    root.wait_window(dialog)

    return result["value"]


def start_bot(root):
    difficulty = choose_bot_difficulty(root)

    if not difficulty:
        return

    root.destroy()
    from briscola_bot import BriscolaGame

    r = tk.Tk()
    icon_ref = load_icon(r)
    r._icon_ref = icon_ref

    game = BriscolaGame(r, initial_difficulty=difficulty)
    if not getattr(game, "app_should_close", False):
        r.mainloop()


def start_online(root):
    root.destroy()
    from briscola_online_client import OnlineBriscolaClient

    r = tk.Tk()
    icon_ref = load_icon(r)
    r._icon_ref = icon_ref

    OnlineBriscolaClient(r)
    r.mainloop()




def load_json_file(path, default):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_profile(profile):
    Path(PROFILE_FILE).write_text(
        json.dumps(profile, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_default_profile():
    return {
        "username": "",
        "online": {
            "partite": 0,
            "vittorie": 0,
            "sconfitte": 0,
            "pareggi": 0,
            "winstreak_attuale": 0,
            "winstreak_migliore": 0,
            "punti_totali_tu": 0,
            "punti_totali_avversario": 0,
            "ultima_partita": None
        }
    }


def get_achievement_rows(bot_stats, online_stats):
    bot_stats = bot_stats or {}
    online_stats = online_stats or {}

    bot_partite = int(bot_stats.get("partite", 0) or 0)
    bot_vittorie = int(bot_stats.get("vittorie", 0) or 0)
    bot_best_ws = int(bot_stats.get("winstreak_migliore", 0) or 0)
    bot_best_score = int(bot_stats.get("miglior_punteggio_tu", 0) or 0)
    bot_margin = int(bot_stats.get("miglior_vittoria_margine", 0) or 0)
    diff_wins = bot_stats.get("vittorie_per_difficolta", {}) or {}

    online_partite = int(online_stats.get("partite", 0) or 0)
    online_vittorie = int(online_stats.get("vittorie", 0) or 0)
    online_best_ws = int(online_stats.get("winstreak_migliore", 0) or 0)
    online_last = online_stats.get("ultima_partita") or {}

    rows = [
        ("Prima mano", bot_partite + online_partite >= 1, "Gioca almeno una partita."),
        ("Primo sangue", bot_vittorie + online_vittorie >= 1, "Vinci almeno una partita."),
        ("Bot battuto", bot_vittorie >= 1, "Vinci una partita contro il bot."),
        ("Bot grinder", bot_vittorie >= 10, "Vinci 10 partite contro il bot."),
        ("Tripletta bot", bot_best_ws >= 3, "Vinci 3 partite consecutive contro il bot."),
        ("Dominatore bot", bot_best_score >= 80, "Arriva ad almeno 80 punti contro il bot."),
        ("Vittoria larga", bot_margin >= 30, "Vinci contro il bot con almeno 30 punti di margine."),
        ("Difficile superato", diff_wins.get("Difficile", 0) >= 1, "Vinci almeno una partita a Difficile."),
        ("Avanzato superato", diff_wins.get("Avanzato", 0) >= 1, "Vinci almeno una partita ad Avanzato."),
        ("Avanzato++ superato", diff_wins.get("Avanzato++", 0) >= 1, "Vinci almeno una partita ad Avanzato++."),
        ("Online: prima partita", online_partite >= 1, "Completa una partita online."),
        ("Online: prima vittoria", online_vittorie >= 1, "Vinci una partita online."),
        ("Online: serie positiva", online_best_ws >= 3, "Vinci 3 partite online consecutive."),
        ("Online: veterano", online_partite >= 10, "Completa 10 partite online."),
        ("Online: martello", online_vittorie >= 10, "Vinci 10 partite online."),
    ]

    try:
        last_margin = int(online_last.get("punti_tu", 0)) - int(online_last.get("punti_avversario", 0))
    except Exception:
        last_margin = 0

    rows.append(("Online: vittoria comoda", last_margin >= 20, "Vinci online con almeno 20 punti di margine."))
    return rows


def format_bot_stats_complete(bot_stats):
    if not bot_stats or int(bot_stats.get("partite", 0) or 0) <= 0:
        return "Nessuna partita contro il bot registrata."

    partite = max(int(bot_stats.get("partite", 0) or 0), 1)
    vittorie = int(bot_stats.get("vittorie", 0) or 0)
    sconfitte = int(bot_stats.get("sconfitte", 0) or 0)
    pareggi = int(bot_stats.get("pareggi", 0) or 0)
    winrate = vittorie / partite * 100

    righe = [
        "STATISTICHE COMPLETE CONTRO IL BOT",
        "",
        f"Partite giocate: {partite}",
        f"Vittorie: {vittorie}",
        f"Sconfitte: {sconfitte}",
        f"Pareggi: {pareggi}",
        f"Percentuale vittorie: {winrate:.1f}%",
        "",
        f"Winstreak attuale: {bot_stats.get('winstreak_attuale', 0)}",
        f"Migliore winstreak: {bot_stats.get('winstreak_migliore', 0)}",
        f"Loss streak attuale: {bot_stats.get('losestreak_attuale', 0)}",
        f"Peggiore loss streak: {bot_stats.get('losestreak_migliore', 0)}",
        "",
        f"Punti medi tuoi: {(bot_stats.get('punti_totali_tu', 0) or 0) / partite:.1f}",
        f"Punti medi bot: {(bot_stats.get('punti_totali_bot', 0) or 0) / partite:.1f}",
        f"Miglior punteggio tuo: {bot_stats.get('miglior_punteggio_tu', 0)}",
        f"Miglior punteggio bot: {bot_stats.get('miglior_punteggio_bot', 0)}",
        f"Vittoria più larga: +{bot_stats.get('miglior_vittoria_margine', 0)}",
        f"Sconfitta peggiore: -{bot_stats.get('peggior_sconfitta_margine', 0)}",
        "",
        "PER DIFFICOLTÀ",
    ]

    giocate_diff = bot_stats.get("partite_per_difficolta", {}) or {}
    vinte_diff = bot_stats.get("vittorie_per_difficolta", {}) or {}

    for liv in ["Facile", "Medio", "Difficile", "Avanzato", "Avanzato+", "Avanzato++"]:
        giocate = int(giocate_diff.get(liv, 0) or 0)
        vinte = int(vinte_diff.get(liv, 0) or 0)
        wr = (vinte / giocate * 100) if giocate else 0
        righe.append(f"{liv}: {vinte}/{giocate} vinte ({wr:.1f}%)")

    ultima = bot_stats.get("ultima_partita")
    if ultima:
        righe.extend([
            "",
            "ULTIMA PARTITA",
            f"Data: {ultima.get('data', '')}",
            f"Risultato: {ultima.get('risultato', '')}",
            f"Difficoltà: {ultima.get('difficolta', '')}",
            f"Punti: Tu {ultima.get('punti_tu', 0)} | Bot {ultima.get('punti_bot', 0)}",
            f"Mani: Tu {ultima.get('mani_tu', 0)} | Bot {ultima.get('mani_bot', 0)}",
            f"Briscola: {str(ultima.get('briscola', '')).upper()}",
        ])

    return "\n".join(righe)


def format_online_stats_complete(online):
    if not online or int(online.get("partite", 0) or 0) <= 0:
        return "Nessuna partita online registrata."

    partite = max(int(online.get("partite", 0) or 0), 1)
    vittorie = int(online.get("vittorie", 0) or 0)
    sconfitte = int(online.get("sconfitte", 0) or 0)
    pareggi = int(online.get("pareggi", 0) or 0)
    winrate = vittorie / partite * 100

    righe = [
        "STATISTICHE ONLINE COMPLETE",
        "",
        f"Partite giocate: {partite}",
        f"Vittorie: {vittorie}",
        f"Sconfitte: {sconfitte}",
        f"Pareggi: {pareggi}",
        f"Percentuale vittorie: {winrate:.1f}%",
        "",
        f"Winstreak attuale: {online.get('winstreak_attuale', 0)}",
        f"Migliore winstreak: {online.get('winstreak_migliore', 0)}",
        "",
        f"Punti medi tuoi: {(online.get('punti_totali_tu', 0) or 0) / partite:.1f}",
        f"Punti medi avversario: {(online.get('punti_totali_avversario', 0) or 0) / partite:.1f}",
    ]

    ultima = online.get("ultima_partita")
    if ultima:
        righe.extend([
            "",
            "ULTIMA PARTITA ONLINE",
            f"Data: {ultima.get('data', '')}",
            f"Risultato: {ultima.get('risultato', '')}",
            f"Tu: {ultima.get('tu', '')}",
            f"Avversario: {ultima.get('avversario', '')}",
            f"Punti: {ultima.get('punti_tu', 0)} - {ultima.get('punti_avversario', 0)}",
            f"Stanza: {ultima.get('stanza', '')}",
        ])

    return "\n".join(righe)


def format_achievements(bot_stats, online):
    rows = get_achievement_rows(bot_stats, online)
    unlocked = sum(1 for _, ok, _ in rows if ok)

    righe = ["OBIETTIVI", "", f"Sbloccati: {unlocked}/{len(rows)}", ""]
    for name, ok, desc in rows:
        mark = "✓" if ok else "□"
        righe.append(f"{mark} {name}")
        righe.append(f"   {desc}")

    return "\n".join(righe)


def show_text_window(root, title, content):
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.resizable(True, True)

    frame = ttk.Frame(dialog, padding=(14, 14, 14, 14))
    frame.pack(fill="both", expand=True)

    text = tk.Text(frame, width=68, height=30, wrap="word", font=("Consolas", 10))
    text.pack(fill="both", expand=True)
    text.insert("1.0", content)
    text.configure(state="disabled")

    ttk.Button(frame, text="Chiudi", command=dialog.destroy).pack(anchor="e", pady=(10, 0))

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
    dialog.geometry(f"+{x}+{y}")



def show_profile(root):
    default = get_default_profile()

    dialog = tk.Toplevel(root)
    dialog.title("Profilo utente")
    dialog.resizable(False, False)

    frame = ttk.Frame(dialog, padding=(22, 20, 22, 18))
    frame.pack(fill="both", expand=True)

    title = ttk.Label(frame, text="PROFILO UTENTE", font=("Segoe UI", 14, "bold"))
    title.pack(pady=(0, 16))

    def current_profile():
        p = load_json_file(PROFILE_FILE, default)
        p.setdefault("username", "")
        p.setdefault("online", default["online"])
        return p

    def open_edit_username():
        p = current_profile()

        edit = tk.Toplevel(dialog)
        edit.title("Modifica nome utente")
        edit.resizable(False, False)
        edit.transient(dialog)
        edit.grab_set()

        edit_frame = ttk.Frame(edit, padding=(16, 14, 16, 14))
        edit_frame.pack(fill="both", expand=True)

        ttk.Label(edit_frame, text="Nome:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 12))

        name_var = tk.StringVar(value=p.get("username", ""))
        name_entry = ttk.Entry(edit_frame, textvariable=name_var, width=30)
        name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 12))

        buttons = ttk.Frame(edit_frame)
        buttons.grid(row=1, column=0, columnspan=2, sticky="e")

        def ok():
            p2 = current_profile()
            p2["username"] = name_var.get().strip()
            save_profile(p2)
            edit.destroy()

        ttk.Button(buttons, text="OK", width=10, command=ok).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Annulla", width=10, command=edit.destroy).pack(side="left")

        name_entry.focus_set()
        edit.bind("<Return>", lambda event: ok())
        edit.bind("<Escape>", lambda event: edit.destroy())

        edit.update_idletasks()
        x = (edit.winfo_screenwidth() // 2) - (edit.winfo_reqwidth() // 2)
        y = (edit.winfo_screenheight() // 2) - (edit.winfo_reqheight() // 2)
        edit.geometry(f"+{x}+{y}")

    def show_bot_stats():
        show_text_window(
            root,
            "Statistiche bot",
            format_bot_stats_complete(load_json_file(BOT_STATS_FILE, {}))
        )

    def show_online_stats():
        p = current_profile()
        show_text_window(
            root,
            "Statistiche online",
            format_online_stats_complete(p.get("online", default["online"]))
        )

    def show_achievements():
        p = current_profile()
        show_text_window(
            root,
            "Obiettivi",
            format_achievements(
                load_json_file(BOT_STATS_FILE, {}),
                p.get("online", default["online"])
            )
        )

    button_width = 34

    ttk.Button(
        frame,
        text="Modifica nome utente",
        width=button_width,
        command=open_edit_username
    ).pack(pady=5)

    ttk.Button(
        frame,
        text="Statistiche bot",
        width=button_width,
        command=show_bot_stats
    ).pack(pady=5)

    ttk.Button(
        frame,
        text="Statistiche online",
        width=button_width,
        command=show_online_stats
    ).pack(pady=5)

    ttk.Button(
        frame,
        text="Obiettivi",
        width=button_width,
        command=show_achievements
    ).pack(pady=5)

    ttk.Button(
        frame,
        text="Chiudi",
        width=button_width,
        command=dialog.destroy
    ).pack(pady=(16, 0))

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
    dialog.geometry(f"+{x}+{y}")



TUTORIAL_TEXT = """COME SI GIOCA A BRISCOLA

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
1. Scegli la modalità dal menu iniziale.
2. Durante il tuo turno clicca con il mouse su una delle tue tre carte.
3. Il bot o l'avversario giocherà automaticamente.
4. Chi vince la mano prende le carte sul tavolo.
5. Chi vince la mano pesca per primo.
6. Quando il mazzo finisce, si giocano le ultime carte rimaste in mano.
7. Alla fine compare il riepilogo con i punti.

CONSIGLI BASE
- Non sprecare briscole alte su carte che valgono 0.
- Cerca di prendere assi e tre: sono i carichi.
- Se giochi un carico, l'avversario potrebbe prenderlo con una briscola.
- Se devi perdere una mano, prova a perdere con una carta che vale 0.
- Verso fine partita conta molto ricordare quali briscole sono già uscite.

TUTORIAL INTERATTIVO
Nel tutorial interattivo giochi una partita guidata contro il bot.
Il gioco ti suggerisce quale carta giocare e ti spiega il perché.
Puoi scegliere se vedere le carte del bot scoperte o coperte.
"""


def show_textual_tutorial(root):
    dialog = tk.Toplevel(root)
    dialog.title("Tutorial testuale")
    dialog.geometry("660x570")
    dialog.resizable(True, True)

    frame = ttk.Frame(dialog, padding=(14, 14, 14, 14))
    frame.pack(fill="both", expand=True)

    text = tk.Text(frame, wrap="word", font=("Segoe UI", 10), padx=8, pady=8)
    text.pack(fill="both", expand=True)
    text.insert("1.0", TUTORIAL_TEXT)
    text.configure(state="disabled")

    ttk.Button(frame, text="Chiudi", command=dialog.destroy).pack(anchor="e", pady=(10, 0))


def start_interactive_tutorial(root, show_bot_cards):
    root.destroy()
    from briscola_bot import BriscolaGame

    r = tk.Tk()
    icon_ref = load_icon(r)
    r._icon_ref = icon_ref

    game = BriscolaGame(
        r,
        initial_difficulty="Facile",
        tutorial_mode=True,
        tutorial_show_bot_cards=show_bot_cards
    )

    if not getattr(game, "app_should_close", False):
        r.mainloop()


def ask_tutorial_bot_cards(root):
    dialog = tk.Toplevel(root)
    dialog.title("Tutorial interattivo")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=(18, 16, 18, 14))
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="Carte del bot",
        font=("Segoe UI", 12, "bold")
    ).pack(pady=(0, 10))

    ttk.Label(
        frame,
        text="Vuoi vedere le carte del bot scoperte durante il tutorial?",
        font=("Segoe UI", 9)
    ).pack(pady=(0, 14))

    buttons = ttk.Frame(frame)
    buttons.pack()

    def choose(value):
        dialog.destroy()
        start_interactive_tutorial(root, value)

    ttk.Button(buttons, text="Scoperte", width=14, command=lambda: choose(True)).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Coperte", width=14, command=lambda: choose(False)).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Indietro", width=14, command=dialog.destroy).pack(side="left")

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
    dialog.geometry(f"+{x}+{y}")


def show_tutorial_choice(root):
    dialog = tk.Toplevel(root)
    dialog.title("Tutorial")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=(22, 20, 22, 18))
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="TUTORIAL", font=("Segoe UI", 14, "bold")).pack(pady=(0, 14))
    ttk.Label(frame, text="Scegli che tipo di tutorial vuoi aprire.", font=("Segoe UI", 9)).pack(pady=(0, 18))

    def textual():
        dialog.destroy()
        show_textual_tutorial(root)

    def interactive():
        dialog.destroy()
        ask_tutorial_bot_cards(root)

    ttk.Button(frame, text="Tutorial testuale", width=34, command=textual).pack(pady=5)
    ttk.Button(frame, text="Tutorial interattivo", width=34, command=interactive).pack(pady=5)
    ttk.Button(frame, text="Indietro", width=34, command=dialog.destroy).pack(pady=(16, 0))

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_reqwidth() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_reqheight() // 2)
    dialog.geometry(f"+{x}+{y}")


def main():
    root = tk.Tk()
    root.title("Briscola")
    root.resizable(False, False)
    icon_ref = load_icon(root)
    root._icon_ref = icon_ref

    frame = ttk.Frame(root, padding=(22, 20, 22, 18))
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="BRISCOLA", font=("Segoe UI", 18, "bold")).pack(pady=(0, 14))
    ttk.Label(frame, text="Scegli come vuoi giocare", font=("Segoe UI", 10)).pack(pady=(0, 18))

    ttk.Button(frame, text="Gioca contro il computer", width=34, command=lambda: start_bot(root)).pack(pady=5)
    ttk.Button(frame, text="Gioca online", width=34, command=lambda: start_online(root)).pack(pady=5)
    ttk.Button(frame, text="Tutorial", width=34, command=lambda: show_tutorial_choice(root)).pack(pady=5)
    ttk.Button(frame, text="Profilo utente", width=34, command=lambda: show_profile(root)).pack(pady=5)
    ttk.Button(frame, text="Esci", width=34, command=root.destroy).pack(pady=(16, 0))

    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_reqwidth() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_reqheight() // 2)
    root.geometry(f"+{x}+{y}")
    root.mainloop()


if __name__ == "__main__":
    main()
