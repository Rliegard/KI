#############################################################################################
# MODULINFORMATIONEN
#############################################################################################
# Modul:       ki_web_analyser.py
# Projekt:     Wissens-KI Prototyp (Web-Analyse und Quellvergleich)
#
# Beschreibung: Dieses Modul implementiert eine Tkinter-GUI zur Durchführung von
#               zielgerichteten Web-Suchen und Inhaltsanalysen. Es simuliert den
#               Abruf von "Wissen" aus verschiedenen Quelltypen (Wissen, Forschung, Allgemein)
#               mithilfe von DuckDuckGo Search, Requests und BeautifulSoup.
#               Die Suche läuft in einem separaten Thread, um die GUI-Reaktionsfähigkeit zu gewährleisten.
#
# Autor:       Rainer Liegard
# Organisation: KI-Entwicklung
# Erstellt:     2025-10-30
# Version:     1.0.0
# Lizenz:      [Bitte Lizenz festlegen, z.B. Proprietär oder MIT]
#
# Abhängigkeiten: tkinter, threading, requests, bs4, duckduckgo_search
#############################################################################################


import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import time
import random

# ===================================================================
# 1. SETUP & KONSTANTEN (User-Agents, Proxy)
# ===================================================================

# --- Liste der User-Agents zur Verschleierung ---
USER_AGENT_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Definiere den Proxy hier (Optional)
PROXY_ADRESSE = None

# ===================================================================
# 2. WEB SCRAPING (Inhaltsextraktion)
# ===================================================================

def get_text_from_url(url):
    """
    Holt den reinen Text von einer URL und verschleiert den Client.
    Verwendet BeautifulSoup zur Bereinigung von Skript-Tags und Navigation.
    """
    try:
        random_user_agent = random.choice(USER_AGENT_POOL)
        headers = {'User-Agent': random_user_agent}

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Entfernt irrelevante Elemente wie Skripte, Styles, Navigation etc.
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        text = soup.body.get_text(separator=' ', strip=True)
        cleaned_text = ' '.join(text.split())

        if not cleaned_text:
            return "[Konnte keinen lesbaren Text von dieser URL extrahieren]"

        # Beschränke die Textlänge, um die Ausgabe übersichtlich zu halten
        return cleaned_text[:1500]
    except requests.exceptions.HTTPError as http_err:
        return f"[Fehler: Die Seite {url} hat den Zugriff verweigert (Code: {http_err.response.status_code})]"
    except Exception as e:
        return f"[Fehler beim Laden von {url}: {type(e).__name__}]"

# ===================================================================
# 3. WISSENSABRUF (DuckDuckGo Search)
# ===================================================================

def ki_wissensabruf_und_vergleich(anfrage, quelle_typ):
    """
    Führt eine Suche durch, schränkt diese nach Quelltyp ein und
    simuliert die KI-Erkenntnis durch die Extraktion des Inhalts der Top-Quelle.
    """

    # Füge explizit die Sprache hinzu, um irrelevante Sprachen zu reduzieren
    suchanfrage = f"{anfrage} language:de"

    if quelle_typ == "Wissen (Wikipedia, Spektrum, .edu)":
        suchanfrage = f"{anfrage} site:wikipedia.org OR site:spektrum.de OR site:*.edu language:de"
    elif quelle_typ == "Forschung (PubMed, Nature)":
        # Forschungssuche wird nicht auf Deutsch eingeschränkt, da englische Quellen dominieren
        suchanfrage = f"{anfrage} site:nature.com OR site:pubmed.ncbi.nlm.nih.gov OR site:sciencemag.org"

    try:
        # 1. Zufällige Verzögerung zur Vermeidung von Blockaden
        zufaellige_pause = random.uniform(2, 6)
        print(f"Warte {zufaellige_pause:.2f} Sekunden...")
        time.sleep(zufaellige_pause)

        results = []

        # 2. Websuche durchführen
        with DDGS(timeout=10, proxy=PROXY_ADRESSE) as ddgs:
            results = list(ddgs.text(suchanfrage, max_results=3))

        if not results:
            return "Keine relevanten Online-Dokumente für diese spezifische Anfrage und Quelle gefunden.\n\n(Häufigster Grund: DuckDuckGo blockiert automatisierte Anfragen (IP-Sperre) oder es gibt wirklich keine Treffer für die Suchkombination.)"

        # 3. Verarbeitung der Ergebnisse (Extraktion der Top-Quelle)
        erkenntnis = f"Erkenntnis-Simulation basierend auf {len(results)} Dokumenten:\n\n"

        first_result = results[0]
        first_url = first_result.get('href')

        if not first_url:
            erkenntnis += "Erstes Ergebnis hatte keine URL."
            return erkenntnis

        inhalt = get_text_from_url(first_url)

        erkenntnis += f"Top-Quelle ({first_result.get('title', 'Kein Titel') }):\n"
        erkenntnis += f"'{inhalt[:300]}...' (Quelle: {first_url})\n\n"

        erkenntnis += "Weitere gefundene Quellen:\n"
        for res in results[1:]:
            erkenntnis += f"- {res.get('title', 'Kein Titel')} ({res.get('href', 'Keine URL')})\n"

        return erkenntnis

    except Exception as e:
        return f"FEHLER BEI DER INTERNET-SUCHE:\n\n{type(e).__name__}: {e}\n\nDies wird oft durch ein IP-Block von DuckDuckGo, eine fehlende Internetverbindung oder eine Firewall verursacht. \n\nVersuchen Sie es in ein paar Minuten erneut oder starten Sie das Programm neu."

# ===================================================================
# 4. GUI HILFSFUNKTIONEN (Tooltip-Klasse)
# ===================================================================

class Tooltip:
    """Erstellt einen Tooltip für ein Tkinter-Widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.close)
        self.tw = None

    def enter(self, event=None): self.schedule()
    def schedule(self):
        self.unschedule()
        self.tw = self.widget.after(500, self.show)
    def unschedule(self):
        if self.tw: self.widget.after_cancel(self.tw)
        self.tw = None
    def show(self):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tw, text=self.text, justify='left',
                          background="#ffffe0", relief='solid', borderwidth=1,
                          font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)
    def close(self, event=None):
        self.unschedule()
        if self.tw: self.tw.destroy()
        self.tw = None


# ===================================================================
# 5. BENUTZEROBERFLÄCHE (Tkinter/GUI-Klasse)
# ===================================================================

class WissensKI_GUI:
    """Die Haupt-GUI-Klasse für die Anwendung, die das Layout und die Interaktionen verwaltet."""
    def __init__(self, master):
        self.master = master
        master.title("Wissens-KI (Prototyp)")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(master, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        # 1. Eingabebereich
        ttk.Label(main_frame, text="Ihre Anfrage:").grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self.anfrage_entry = ttk.Entry(main_frame, width=60)
        self.anfrage_entry.insert(0, "Was sind die drei Mendelschen Regeln und wofür stehen sie?")
        self.anfrage_entry.grid(row=1, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))
        self.anfrage_entry.focus()
        Tooltip(self.anfrage_entry, "Geben Sie eine Frage oder These ein, die mit wissenschaftlichen Seiten verglichen werden soll.")

        # 2. Dropdown (Quelle)
        ttk.Label(main_frame, text="Wissensquelle:").grid(row=2, column=0, sticky=tk.W)
        self.quelle_typ = tk.StringVar(main_frame)
        quellen = ["Wissen (Wikipedia, Spektrum, .edu)", "Allgemeine Suche", "Forschung (PubMed, Nature)"]
        self.quelle_typ.set(quellen[0])
        self.quelle_dropdown = ttk.OptionMenu(main_frame, self.quelle_typ, quellen[0], *quellen)
        self.quelle_dropdown.grid(row=3, column=0, pady=5, sticky=(tk.W, tk.E))
        Tooltip(self.quelle_dropdown, "Wählen Sie den Typ der zu durchsuchenden Quelle aus.")

        # 3. Suchen-Button und Hotkey
        self.suchen_button = ttk.Button(main_frame, text="Suchen (Ctrl+S)", command=self.starte_suche_thread)
        self.suchen_button.grid(row=3, column=1, pady=5, sticky=tk.E)
        master.bind('<Control-s>', lambda event: self.starte_suche_thread())
        Tooltip(self.suchen_button, "Startet den KI-Vergleichsprozess mit der gewählten Quelle.")

        # 4. Ausgabe-Bereich
        ttk.Label(main_frame, text="KI-Erkenntnis:").grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        text_frame = ttk.Frame(main_frame)
        text_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.ausgabe_text = tk.Text(text_frame, wrap=tk.WORD, height=15, state='disabled')
        self.ausgabe_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.ausgabe_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.ausgabe_text['yscrollcommand'] = scrollbar.set

    def starte_suche_thread(self):
        """Startet die Websuche in einem separaten Thread, damit die GUI nicht einfriert."""
        anfrage = self.anfrage_entry.get()
        if not anfrage:
            messagebox.showwarning("Eingabefehler", "Bitte geben Sie eine Anfrage ein.")
            return
        self.suchen_button.config(state='disabled')
        self.ausgabe_text.config(state='normal')
        self.ausgabe_text.delete(1.0, tk.END)
        self.ausgabe_text.insert(tk.END, "Suche und analysiere... (Dies kann einige Sekunden dauern)")
        self.ausgabe_text.config(state='disabled')
        # Startet die langwierige Suche im Hintergrund
        threading.Thread(target=self.fuehre_suche_aus, args=(anfrage,), daemon=True).start()

    def fuehre_suche_aus(self, anfrage):
        """Ruft die Backend-Logik auf."""
        quelle = self.quelle_typ.get()
        ergebnis = ki_wissensabruf_und_vergleich(anfrage, quelle)
        # Sendet das Ergebnis zurück an den Haupt-Thread zur GUI-Aktualisierung
        self.master.after(0, self.aktualisiere_ausgabe, ergebnis)

    def aktualisiere_ausgabe(self, ergebnis):
        """Aktualisiert das Textfeld in der GUI und reaktiviert den Button."""
        self.ausgabe_text.config(state='normal')
        self.ausgabe_text.delete(1.0, tk.END)
        self.ausgabe_text.insert(tk.END, ergebnis)
        self.ausgabe_text.config(state='disabled')
        self.suchen_button.config(state='normal')

# ===================================================================
# 6. THREADING & STARTPUNKT (Main Loop)
# ===================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = WissensKI_GUI(root)
    root.mainloop()
