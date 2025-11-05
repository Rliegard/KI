##################################################################################################
# VERSION:     KI.M2
# ERSTELLT:    2025-10-30
# BESCHREIBUNG: Major-Update: Einführung von Caching und Robustheit.
#               1. SQLite-Integration (`wissens_ki_cache.db`) zur Speicherung aller
#                  erfolgreichen Anfragen und Ergebnisse.
#               2. Implementierung der `googletrans`-Übersetzungslogik, um Inhalte
#                  aus fremdsprachigen Quellen automatisch ins Deutsche zu übersetzen.
#               3. Anti-Block-Logik: Erweiterung um eine Proxy-Pool-Unterstützung (optional)
#                  und eine zweistufige Fallback-Suchstrategie (Spezifisch -> Allgemein) zur
#                  Erhöhung der Erfolgsrate.
#               4. Scraping-Verbesserung: Erweiterte Content-Validierung (Mindestlänge,
#                  Prüfung auf Weiterleitungs-Phrasen) für eine höhere Textqualität.
# Autor: Rainer Liegard
###################################################################################################

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import time
import random
import sqlite3
from googletrans import Translator
# Die problematischen Google-Imports wurden entfernt.

# --- GLOBALE KONSTANTEN UND LISTEN ---
DB_NAME = "wissens_ki_cache.db"

# Liste der User-Agents zur Verschleierung (erweitert)
USER_AGENT_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:56.0) Gecko/20100101 Firefox/56.0',
    'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]

# Liste von Proxies
# WICHTIG: Ersetzen Sie dies durch Ihre eigenen, stabilen Proxys.
PROXY_POOL = [
    None,
    # 'http://user:pass@ip:port',
    # 'socks5://ip:port',
]

# -------------------------------------------------------------------

## 💾 SQLite-Datenbank-Logik

def initialize_db():
    """Erstellt die SQLite-Datenbank und die Tabelle, falls sie noch nicht existiert."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anfragen_cache (
                id INTEGER PRIMARY KEY,
                anfrage TEXT NOT NULL,
                quelle_typ TEXT NOT NULL,
                ergebnis_text TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Fehler beim Initialisieren der Datenbank: {e}")
        return False

def save_to_db(anfrage, quelle_typ, ergebnis_text):
    """Speichert die Anfrage und das Ergebnis in die Datenbank."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO anfragen_cache (anfrage, quelle_typ, ergebnis_text) VALUES (?, ?, ?)",
                       (anfrage, quelle_typ, ergebnis_text))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Fehler beim Speichern in die Datenbank: {e}")

## 🌐 Übersetzung-Logik

def translate_to_german(text):
    """Übersetzt den gegebenen Text ins Deutsche."""
    try:
        if not text:
            return ""
        translator = Translator()
        detection = translator.detect(text[:100])
        if detection.lang == 'de':
            return text

        # Begrenzung des Textes, da googletrans sonst fehlschlagen kann
        translation = translator.translate(text[:5000], dest='de')
        return translation.text
    except Exception as e:
        return f"[Übersetzungsfehler: {type(e).__name__} - Installation von googletrans prüfen. Der Originaltext folgt.]\n\nOriginal:\n{text}"

## 🔍 BACKEND-LOGIK (Web-Suche und Scraping)

def get_text_from_url(url, current_proxy=None):
    """
    Holt den reinen Text von einer URL und verschleiert den Client.
    Gibt (Text, bool_success) zurück.
    """

    # 1. Zufällige Verzögerung vor dem Scraping
    time.sleep(random.uniform(1.5, 3.5))

    # Definierte Texte, die als leer oder Redirect-Text gelten
    INVALID_CONTENT_PHRASES = [
        "bitte klicken sie hier",
        "nicht automatisch weitergeleitet",
        "click here if you are not redirected",
        "redirecting",
        "weiterleiten",
        "cookie",
        "404 not found"
    ]

    try:
        random_user_agent = random.choice(USER_AGENT_POOL)
        headers = {
            'User-Agent': random_user_agent,
            'Referer': 'https://duckduckgo.com/',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7'
        }

        proxies = {"http": current_proxy, "https": current_proxy} if current_proxy else None

        # requests folgt standardmäßig HTTP-Redirects
        response = requests.get(url, headers=headers, timeout=15, proxies=proxies)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Entfernen irrelevanter HTML-Elemente
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            element.decompose()

        text = soup.body.get_text(separator=' ', strip=True)
        cleaned_text = ' '.join(text.split())

        # NEUE VALIDIERUNGEN:
        # 1. Prüfen auf Mindestlänge des extrahierten Textes
        if len(cleaned_text) < 70:
            return f"[Konnte keinen substanziellen Text von dieser URL extrahieren - Länge: {len(cleaned_text)}]", False

        # 2. Prüfen auf bekannte Weiterleitungsphrasen
        lower_text = cleaned_text.lower()
        if any(phrase in lower_text for phrase in INVALID_CONTENT_PHRASES):
            return f"[Ungültiger Inhalt erkannt: Weiterleitungs- oder Platzhalter-Text.]", False

        return cleaned_text, True

    except requests.exceptions.HTTPError as http_err:
        error_msg = f"[Fehler: Die Seite {url} hat den Zugriff verweigert (Code: {http_err.response.status_code})]"
        # Markiere 403 als Fehlschlag
        return error_msg, (http_err.response.status_code != 403)

    except Exception as e:
        error_msg = f"[Fehler beim Laden von {url}: {type(e).__name__}]"
        return error_msg, False

def ki_wissensabruf_und_vergleich(anfrage, quelle_typ):
    """
    Führt eine Suche durch mit DDGS mit zwei Fallback-Strategien.
    Geht die Suchergebnisse durch, bis eine Quelle erfolgreich geladen werden kann.
    """
    # Max. 2 Versuche (statt 3), um den Bing-Fallback zu vermeiden.
    MAX_RETRIES = 2

    # Standard-Einstellung für definitorische oder allgemeine Fragen.
    suchanfrage_spezifisch = anfrage

    # Nur spezifische Filter anwenden, wenn es sich NICHT um eine einfache Frage handelt
    # UND die Quelle "Wissen" oder "Forschung" ist.
    is_simple_question = anfrage.lower().startswith(("was ist", "was bedeutet", "wer ist", "def", "definition"))

    if not is_simple_question:
        if quelle_typ == "Wissen (Wikipedia, Spektrum, .edu)":
            suchanfrage_spezifisch = f"{anfrage} site:wikipedia.org OR site:spektrum.de OR site:*.edu language:de"
        elif quelle_typ == "Forschung (PubMed, Nature)":
            suchanfrage_spezifisch = f"{anfrage} site:nature.com OR site:pubmed.ncbi.nlm.nih.gov OR site:sciencemag.org"
        # Andernfalls bleibt es die allgemeine Anfrage

    # Starte die Suche mit verschiedenen Strategien (DDGS Spezifisch/Gefiltert, DDGS Fallback/Allgemein)
    for retry_count in range(MAX_RETRIES):
        current_proxy = random.choice(PROXY_POOL) if PROXY_POOL and random.random() < 0.7 else None
        results = []

        # Festlegen der effektiven Suchanfrage und des Dienstes
        if retry_count == 0:
            suchanfrage_effektiv = suchanfrage_spezifisch
            dienst_name = "DDGS (Spezifisch/Gefiltert)"
            threading.current_thread().name = 'ddgs_search_thread_0'
        else: # retry_count == 1
            # Im zweiten Versuch nur die reine Anfrage ohne Filter verwenden, um die Erfolgschance zu erhöhen.
            suchanfrage_effektiv = anfrage
            dienst_name = "DDGS (Fallback/Allgemein)"
            threading.current_thread().name = 'ddgs_search_thread_1'


        zufaellige_pause = random.uniform(3 + retry_count * 2, 8 + retry_count * 2)
        print(f"INFO: {dienst_name} Versuch ({retry_count + 1}). Warte {zufaellige_pause:.2f}s mit Proxy: {current_proxy if current_proxy else 'Kein Proxy'}")
        time.sleep(zufaellige_pause)

        try:
            # SUCHE DURCHFÜHREN
            with DDGS(timeout=20, proxy=current_proxy) as ddgs:
                results = list(ddgs.text(suchanfrage_effektiv, max_results=5))

            if not results:
                print(f"WARN: {dienst_name} lieferte keine Suchergebnisse.")
                # Wenn im letzten Versuch keine Ergebnisse geliefert werden, geben wir eine Fehlermeldung zurück
                if retry_count == MAX_RETRIES - 1:
                    return "Keine Suchergebnisse gefunden. Versuchen Sie es mit einer allgemeineren Anfrage."
                continue

            # QUELLE LADEN UND VERARBEITEN
            successful_result = None
            successful_content = None

            for i, result in enumerate(results):
                first_url = result.get('href')
                if not first_url:
                    continue

                print(f"INFO: Versuche, Quelle #{i+1} zu laden: {first_url}")

                inhalt, success = get_text_from_url(first_url, current_proxy)

                if success:
                    successful_result = result
                    successful_content = inhalt
                    break
                else:
                    print(f"WARN: Laden von {first_url} fehlgeschlagen: {inhalt}")

            # WENN ERFOLGREICH
            if successful_result and successful_content:

                uebersetzter_inhalt = translate_to_german(successful_content)

                erkenntnis = f"Erkenntnis-Simulation (Quelle: {quelle_typ}, Dienst: {dienst_name}, Versuch {retry_count + 1}):\n\n"

                # FOKUSSIERTE ANTWORT (begrenzt auf 500 Zeichen)
                erkenntnis += f"--- ANTWORT (ZUSAMMENFASSUNG):\n"

                display_text = uebersetzter_inhalt[:500]
                if len(uebersetzter_inhalt) > 500:
                    display_text += '...'

                erkenntnis += f"\n**{display_text.strip()}**\n\n"

                # QUELLE
                erkenntnis += f"--- QUELLE DER ERKENNTNIS:\n"
                erkenntnis += f"Titel: {successful_result.get('title', 'Kein Titel')} \n"
                erkenntnis += f"URL: {successful_result.get('href')}\n\n"

                # Weitere gefundene Quellen
                erkenntnis += "Weitere gefundene Quellen (ungeladen oder blockiert):\n"
                for res in results:
                    if res != successful_result:
                        erkenntnis += f"- {res.get('title', 'Kein Titel')} ({res.get('href', 'Keine URL')})\n"

                save_to_db(anfrage, quelle_typ, erkenntnis)
                return erkenntnis

            # WENN KEINE QUELLE innerhalb dieses Versuchs geladen werden konnte:
            if retry_count == MAX_RETRIES - 1:
                return f"Keine Online-Dokumente extrahiert.\n\n(Alle {len(results)} Quellen aus dem letzten Versuch wurden blockiert oder lieferten keinen substanziellen Text. Versuchen Sie es mit einer allgemeineren Anfrage.)"

        except Exception as e:
            error_message = f"FEHLER BEI INTERNET-SUCHE auf {dienst_name} (Versuch {retry_count + 1}): {type(e).__name__}: {e}"
            print(error_message)

            if retry_count == MAX_RETRIES - 1:
                return f"FEHLER NACH ALLEN VERSUCHEN:\n\n{error_message}\n\nEs konnte keine Verbindung zu einem Suchdienst hergestellt werden."

    # Diese Zeile wurde entfernt, da die Logik in den Try/Except-Blöcken alle Fälle abdeckt.
    # return "Fehlerhafte Programmsteuerung." # <--- Entfernt

## 🖼️ GUI-LOGIK (Tkinter)

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

class WissensKI_GUI:
    """Die Haupt-GUI-Klasse für die Anwendung."""
    def __init__(self, master):
        self.master = master
        master.title("Wissens-KI (Prototyp mit Anti-Block-Logik)")

        # Datenbank beim Start initialisieren
        if not initialize_db():
            messagebox.showerror("Datenbankfehler", "Konnte die SQLite-Datenbank nicht initialisieren. Programm wird beendet.")
            master.quit()
            return

        # Rest der GUI-Initialisierung
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(master, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        # 1. Eingabebereich
        ttk.Label(main_frame, text="Ihre Anfrage:").grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self.anfrage_entry = ttk.Entry(main_frame, width=60)

        # Beispiel-Anfrage angepasst
        self.anfrage_entry.insert(0, "Was bedeutet die chemische Formel H2O?")

        self.anfrage_entry.grid(row=1, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))
        self.anfrage_entry.focus()
        Tooltip(self.anfrage_entry, "Geben Sie eine Frage oder These ein, die mit wissenschaftlichen Seiten verglichen werden soll. Der Inhalt wird automatisch übersetzt.")

        # 2. Dropdown (Quelle)
        ttk.Label(main_frame, text="Wissensquelle:").grid(row=2, column=0, sticky=tk.W)
        self.quelle_typ = tk.StringVar(main_frame)

        # 🟢 Korrigierte Position
        quellen = ["Wissen (Wikipedia, Spektrum, .edu)", "Allgemeine Suche", "Forschung (PubMed, Nature)"]

        self.quelle_typ.set(quellen[0])
        self.quelle_dropdown = ttk.OptionMenu(main_frame, self.quelle_typ, quellen[0], *quellen)
        self.quelle_dropdown.grid(row=3, column=0, pady=5, sticky=(tk.W, tk.E))
        Tooltip(self.quelle_dropdown, "Wählen Sie den Typ der zu durchsuchenden Quelle aus.")

        # 3. Suchen-Button und Hotkey
        self.suchen_button = ttk.Button(main_frame, text="Suchen (Ctrl+S)", command=self.starte_suche_thread)
        self.suchen_button.grid(row=3, column=1, pady=5, sticky=tk.E)
        master.bind('<Control-s>', lambda event: self.starte_suche_thread())
        Tooltip(self.suchen_button, "Startet den KI-Vergleichsprozess. Das Ergebnis wird gespeichert.")

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
        self.ausgabe_text.insert(tk.END, "Suche, analysiere, **übersetze** und speichere... (Es werden bis zu 2 Versuche unternommen)")
        self.ausgabe_text.config(state='disabled')
        threading.Thread(target=self.fuehre_suche_aus, args=(anfrage,), daemon=True).start()

    def fuehre_suche_aus(self, anfrage):
        """Ruft die Backend-Logik auf."""
        quelle = self.quelle_typ.get()
        ergebnis = ki_wissensabruf_und_vergleich(anfrage, quelle)
        self.master.after(0, self.aktualisiere_ausgabe, ergebnis)

    def aktualisiere_ausgabe(self, ergebnis):
        """Aktualisiert das Textfeld in der GUI."""
        self.ausgabe_text.config(state='normal')
        self.ausgabe_text.delete(1.0, tk.END)
        self.ausgabe_text.insert(tk.END, ergebnis)
        self.ausgabe_text.config(state='disabled')
        self.suchen_button.config(state='normal')


## 🚀 ANWENDUNG STARTEN

if __name__ == "__main__":
    root = tk.Tk()
    app = WissensKI_GUI(root)
    root.mainloop()