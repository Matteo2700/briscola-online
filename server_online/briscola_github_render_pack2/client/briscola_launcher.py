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


def start_bot(root):
    root.destroy()
    from briscola_bot import BriscolaGame

    r = tk.Tk()
    icon_ref = load_icon(r)
    r._icon_ref = icon_ref

    game = BriscolaGame(r)
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



def show_profile(root):
    default = {"username": "", "online": {"partite": 0, "vittorie": 0, "sconfitte": 0, "pareggi": 0, "winstreak_attuale": 0}}

    try:
        profile = json.loads(Path(PROFILE_FILE).read_text(encoding="utf-8")) if Path(PROFILE_FILE).exists() else default
    except Exception:
        profile = default

    profile.setdefault("username", "")
    profile.setdefault("online", default["online"])

    dialog = tk.Toplevel(root)
    dialog.title("Profilo utente")
    dialog.resizable(False, False)

    frame = ttk.Frame(dialog, padding=(18, 16, 18, 14))
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Nome utente fisso").grid(row=0, column=0, sticky="w")
    username_var = tk.StringVar(value=profile.get("username", ""))
    ttk.Entry(frame, textvariable=username_var, width=30).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    text = tk.Text(frame, width=54, height=20, wrap="word", font=("Consolas", 10))
    text.grid(row=1, column=0, columnspan=2, pady=(12, 0))

    def make_summary():
        online = profile.get("online", {})
        bot_txt = "Nessuna statistica bot trovata."

        if Path(BOT_STATS_FILE).exists():
            try:
                bot = json.loads(Path(BOT_STATS_FILE).read_text(encoding="utf-8"))
                bot_txt = (
                    f"Partite: {bot.get('partite', 0)}\n"
                    f"Vittorie: {bot.get('vittorie', 0)}\n"
                    f"Sconfitte: {bot.get('sconfitte', 0)}\n"
                    f"Pareggi: {bot.get('pareggi', 0)}\n"
                    f"Winstreak: {bot.get('winstreak_attuale', 0)}"
                )
            except Exception:
                pass

        return (
            "PROFILO UTENTE\n\n"
            f"Nome utente fisso: {profile.get('username') or '(non impostato)'}\n\n"
            "CONTRO BOT\n"
            f"{bot_txt}\n\n"
            "ONLINE\n"
            f"Partite: {online.get('partite', 0)}\n"
            f"Vittorie: {online.get('vittorie', 0)}\n"
            f"Sconfitte: {online.get('sconfitte', 0)}\n"
            f"Pareggi: {online.get('pareggi', 0)}\n"
            f"Winstreak: {online.get('winstreak_attuale', 0)}"
        )

    def refresh():
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", make_summary())
        text.configure(state="disabled")

    def save():
        profile["username"] = username_var.get().strip()
        Path(PROFILE_FILE).write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        refresh()

    refresh()

    btns = ttk.Frame(frame)
    btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
    ttk.Button(btns, text="Salva nome", command=save).pack(side="left", padx=(0, 8))
    ttk.Button(btns, text="Chiudi", command=dialog.destroy).pack(side="right")

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
    ttk.Button(frame, text="Profilo utente", width=34, command=lambda: show_profile(root)).pack(pady=5)
    ttk.Button(frame, text="Esci", width=34, command=root.destroy).pack(pady=(16, 0))

    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_reqwidth() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_reqheight() // 2)
    root.geometry(f"+{x}+{y}")
    root.mainloop()


if __name__ == "__main__":
    main()
