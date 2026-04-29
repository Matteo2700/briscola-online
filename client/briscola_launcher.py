import tkinter as tk
from tkinter import ttk
from pathlib import Path
from PIL import Image, ImageTk

ICON_FILES = ["icona.ico", "icon.ico", "icona.png", "icon.png"]

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
    ttk.Button(frame, text="Esci", width=34, command=root.destroy).pack(pady=(16, 0))

    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_reqwidth() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_reqheight() // 2)
    root.geometry(f"+{x}+{y}")
    root.mainloop()


if __name__ == "__main__":
    main()
