import tkinter as tk
from pathlib import Path

from briscola_bot import (
    BriscolaGame,
    CARD_W,
    CARD_H,
    GOLD,
    WHITE,
    BLACKISH,
    TABLE_LIGHT,
)


class TutorialBriscolaGame(BriscolaGame):
    """
    Tutorial interattivo separato dal gioco contro bot.

    Nota importante:
    - NON modifica briscola_bot.py
    - NON salva statistiche
    - NON tocca on_move / bot_move / animazioni base
    - se il tutorial avesse un problema, il gioco normale resta pulito
    """

    def __init__(self, root, show_bot_cards=False):
        self.tutorial_show_bot_cards = bool(show_bot_cards)

        # Uso Medio: abbastanza sensato, ma non troppo aggressivo.
        super().__init__(root, initial_difficulty="Medio")

        self.root.title("Briscola - Tutorial interattivo")
        self.training_mode.set(False)
        self.debug_bot.set(self.tutorial_show_bot_cards)
        self.tutorial_last_tip = ""

        self.render()

    # --------------------------------------------------------
    # Il tutorial non deve sporcare statistiche/trofei.
    # --------------------------------------------------------
    def record_stats(self, result_key):
        self.trofei_sbloccati_ultima_partita = []
        return

    def save_settings(self):
        # Non salvo impostazioni dalla modalità tutorial.
        return

    # --------------------------------------------------------
    # Evito tooltip hover: il suggerimento è fisso nel box.
    # Questo evita anche render continui quando il mouse passa sulle carte.
    # --------------------------------------------------------
    def show_training_tip(self, idx):
        return

    def clear_training_tip(self):
        return

    # --------------------------------------------------------
    # Suggerimento didattico.
    # --------------------------------------------------------
    def get_tutorial_recommendation(self):
        if not getattr(self, "turn_player", False) or getattr(self, "lock", False):
            return None, "Aspetta: ora tocca al bot."

        if not getattr(self, "player", None):
            return None, ""

        mano = list(self.player)
        briscola = self.seme_briscola

        def lowest(cards):
            return min(cards, key=lambda c: (c.punti, c.seme == briscola, c.forza)) if cards else None

        def card_index(card):
            try:
                return self.player.index(card)
            except ValueError:
                return None

        # ----------------------------------------------------
        # CASO 1: apri tu la mano.
        # ----------------------------------------------------
        if self.c_b is None:
            lisce_nb = [c for c in mano if c.seme != briscola and c.punti == 0]
            figure_nb = [c for c in mano if c.seme != briscola and 0 < c.punti < 10]
            non_briscole = [c for c in mano if c.seme != briscola]
            briscole_basse = [c for c in mano if c.seme == briscola and c.punti == 0]
            briscole_figure = [c for c in mano if c.seme == briscola and 0 < c.punti < 10]

            if lisce_nb:
                card = lowest(lisce_nb)
                reason = "Apri con una liscia non briscola: rischi poco e non regali punti."
            elif figure_nb:
                card = lowest(figure_nb)
                reason = "Apri con una figura non briscola: vale pochi punti e conservi briscole e carichi."
            elif non_briscole:
                card = lowest(non_briscole)
                reason = "Non hai scarti perfetti: apri con la non briscola meno preziosa."
            elif briscole_basse:
                card = lowest(briscole_basse)
                reason = "Hai solo briscole o quasi: usa la briscola più bassa."
            elif briscole_figure:
                card = lowest(briscole_figure)
                reason = "Hai una mano scomoda: sacrifica la briscola meno importante."
            else:
                card = lowest(mano)
                reason = "Hai solo carte pesanti: scegli quella meno dannosa."

            return card_index(card), reason

        # ----------------------------------------------------
        # CASO 2: il bot ha aperto, tu rispondi.
        # ----------------------------------------------------
        bot_card = self.c_b
        vincenti = [c for c in mano if self.get_winner_logic(c, bot_card) == "player"]

        vincenti_nb = [c for c in vincenti if c.seme != briscola]
        vincenti_b = [c for c in vincenti if c.seme == briscola]

        lisce = [c for c in mano if c.punti == 0]
        lisce_nb = [c for c in mano if c.seme != briscola and c.punti == 0]

        # Se il bot ha giocato asso o tre, prendilo quasi sempre se puoi.
        if bot_card.punti >= 10:
            if vincenti_nb:
                # Se posso prendere senza briscola, anche con asso/tre, è spesso corretto:
                # sto rispondendo per secondo e porto a casa molti punti.
                card = min(vincenti_nb, key=lambda c: (c.punti, c.forza))
                reason = "Il bot ha giocato un carico: prendilo senza usare briscola."
            elif vincenti_b:
                card = min(vincenti_b, key=lambda c: (c.punti, c.forza))
                reason = "Il bot ha giocato un carico: usa la briscola più bassa che prende."
            else:
                card = lowest(lisce_nb or lisce or mano)
                reason = "Non puoi prendere il carico: scarta la carta meno preziosa."

            return card_index(card), reason

        # Se il bot ha giocato una figura, prendere con asso/tre dello stesso seme può andare bene:
        # il tuo carico non lo stai regalando, lo stai incassando.
        if bot_card.punti > 0:
            # Prima prova a prendere senza briscola.
            if vincenti_nb:
                # Preferisci una carta vincente non briscola.
                # Se l'unica che prende è asso/tre, va comunque bene quando prendi punti.
                card = min(vincenti_nb, key=lambda c: (c.punti >= 10, c.punti, c.forza))
                reason = "Ci sono punti sul tavolo: prendili senza usare briscola."
                return card_index(card), reason

            # Poi valuta briscola bassa/figura, ma non sprecare asso/tre di briscola su pochi punti.
            briscole_sacrificabili = [c for c in vincenti_b if c.punti < 10]
            if briscole_sacrificabili and bot_card.punti >= 3:
                card = min(briscole_sacrificabili, key=lambda c: (c.punti, c.forza))
                reason = "Puoi prendere con una briscola sacrificabile: ci sono punti sul tavolo."
                return card_index(card), reason

            card = lowest(lisce_nb or lisce or mano)
            reason = "Non conviene spendere carte importanti per pochi punti: scarta basso."
            return card_index(card), reason

        # Bot ha giocato carta da 0.
        if bot_card.punti == 0:
            # Prendi solo se puoi farlo con carta non preziosa.
            cheap_winners_nb = [c for c in vincenti_nb if c.punti < 10]
            if cheap_winners_nb:
                card = min(cheap_winners_nb, key=lambda c: (c.punti, c.forza))
                reason = "La carta del bot vale 0: puoi prendere senza sprecare un carico."
                return card_index(card), reason

            card = lowest(lisce_nb or lisce or mano)
            reason = "La carta del bot vale 0: non sprecare carichi o briscole, scarta basso."
            return card_index(card), reason

        card = lowest(mano)
        return card_index(card), "Scegli la carta meno costosa."

    # --------------------------------------------------------
    # Disegno: prima il gioco normale, poi box tutorial + bordo carta consigliata.
    # --------------------------------------------------------
    def render(self):
        super().render()

        try:
            real_w = self.canvas.winfo_width()
            real_h = self.canvas.winfo_height()

            w = real_w if real_w > 100 else 1300
            h = real_h if real_h > 100 else 720

            best_idx, reason = self.get_tutorial_recommendation()

            if best_idx is not None and 0 <= best_idx < len(self.player):
                card = self.player[best_idx]
                tip = f"Tutorial: gioca {self.card_to_text(card)}. {reason}"

                pos = self.pos.get(f"player_card_{best_idx}")
                if pos:
                    x, y = pos
                    self.canvas.create_rectangle(
                        x - 5,
                        y - 5,
                        x + CARD_W + 5,
                        y + CARD_H + 5,
                        outline="#00e5ff",
                        width=4
                    )
            else:
                tip = f"Tutorial: {reason}" if reason else "Tutorial: osserva il tavolo e scegli con calma."

            if len(tip) > 215:
                tip = tip[:212] + "..."

            # Box tutorial in basso a sinistra, al posto del vecchio box difficoltà.
            x1 = 75
            y1 = h - 132
            x2 = 545
            y2 = h - 45

            self.rounded_rect(
                x1,
                y1,
                x2,
                y2,
                r=17,
                fill=BLACKISH,
                outline=GOLD,
                width=1
            )

            self.canvas.create_text(
                x1 + 16,
                y1 + 12,
                text=tip,
                fill=WHITE,
                font=("Segoe UI", 9, "bold"),
                width=(x2 - x1) - 32,
                anchor="nw"
            )

        except Exception:
            # Il tutorial non deve mai far crashare il gioco.
            pass

    def exit_game(self, event=None):
        self.return_to_main_menu()
