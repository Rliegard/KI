###########################################################################################
# PROJEKT: Wissens-KI KI.M5
# DATEI:   wissens_ki_gui.py
#
# BESCHREIBUNG:
# Diese Anwendung dient als fortgeschrittenes Tool zur Abfrage, Extraktion,
# Übersetzung und Speicherung von wissenschaftlich relevanten Informationen aus
# dem Internet. Sie kombiniert DuckDuckGo Search (DDGS) für die Suche, Requests
# und BeautifulSoup für das Web-Scraping und googletrans für die automatische
# Übersetzung der Ergebnisse ins Deutsche.
#
# HAUPTFUNKTIONEN:
# 1. Anti-Block-Logik: Implementiert robuste Strategien (User-Agent-Rotation,
#    zufällige Verzögerungen, optionaler Proxy-Einsatz) zur Umgehung von
#    Web-Blocking-Mechanismen und für stabilere Ergebnisse.
# 2. Whitelist/Blacklist: Nutzt Listen, um Suchergebnisse auf seriöse Quellen zu
#    filtern und unzuverlässige Domains auszuschließen.
# 3. Datenbank-Caching: Ergebnisse werden in einer lokalen SQLite-Datenbank
#    gespeichert (anfragen_cache.db).
# 4. Multithreading: Die Suche erfolgt in einem separaten Thread, um die GUI
#    (Tkinter) reaktionsfähig zu halten.
#
# ABHÄNGIGKEITEN:
# - Python 3.x
# - tkinter (Standardbibliothek)
# - requests
# - beautifulsoup4
# - duckduckgo-search
# - googletrans
#
# AUTOR: Rainer Liegard
# Datum: 04.11.2025
###########################################################################################
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
# Die Imports für fpdf2 und os (wegen os.startfile) wurden entfernt

# --- GLOBALE KONSTANTEN UND LISTEN ---
DB_NAME = "wissens_ki_cache.db"

# Liste der Domains, die bekanntermaßen unstrukturierten Text liefern (Blacklist)
UNRELIABLE_DOMAINS = [
    'baidu.com', 'quora.com', 'pinterest.com', 'twitter.com',
    'vk.com', 'reddit.com/r/', 'youtube.com', 'amazon.com', 'aliexpress.com',
]

# Liste der User-Agents zur Verschleierung (erweitert)
USER_AGENT_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:56.0) Gecko/20100101 Firefox/56.0',
    'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version=17.0 Mobile/15E148 Safari/604.1',
]

# ERWEITERT: Statische Liste zuverlässiger, spezialisierter URLs (WHITELIST)
RELIABLE_URL_WHITELIST = [
    # Allgemeine und Bildung
    "https://de.wikipedia.org/",                # Deutsche Wikipedia (Basis-URL für die Suche)
    "https://www.bmbf.de/",                     # Bundesministerium für Bildung und Forschung
    "https://www.destatis.de/",                 # Statistisches Bundesamt
    "https://www.spektrum.de/lexikon/",         # Spektrum.de (Lexika und Wissenschaftsmagazin)

    # Geschichte & Politik
    "https://www.bpb.de/",                      # Bundeszentrale für politische Bildung
    "https://www.bundestag.de/",                # Deutscher Bundestag (Offizielle Dokumente)

    # Naturwissenschaften
    "https://www.umweltbundesamt.de/",          # Umweltbundesamt
    "https://www.mpg.de/",                      # Max-Planck-Gesellschaft (Forschung)
    "https://www.helmholtz.de/",                # Helmholtz-Gemeinschaft (Forschung)
    "https://www.scinexx.de/",                  # Scinexx (Wissenschaftsmagazin)
    "https://www.leibniz-gemeinschaft.de/",     # Leibniz-Gemeinschaft (Forschungsinstitute)

    # Python/Coding
    "https://docs.python.org/3/",               # Offizielle Python-Dokumentation
    "https://www.python-forum.de/",             # Deutsches Python Forum
]

# PROXY-POOL: Nur direkte Verbindung (Rotation deaktiviert)
PROXY_POOL = [
    None, # Direkte Verbindung als einziger Standard-Fallback
]

# --- HILFSFUNKTIONEN ---

def initialize_db():
    """Erstellt die SQLite-Datenbank."""
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

def translate_to_german(text):
    """Übersetzt den gegebenen Text ins Deutsche."""
    try:
        if not text:
            return ""
        translator = Translator()
        # Begrenzung des Texts für Google Translate API
        translation = translator.translate(text[:5000], dest='de')
        return translation.text
    except Exception as e:
        return f"[Übersetzungsfehler: {type(e).__name__} - Originaltext folgt.]\n\nOriginal:\n{text}"


## 🔍 BACKEND-LOGIK (Web-Suche und Scraping)

def get_text_from_url(url, current_proxy=None):
    """
    Holt den reinen Text von einer URL, fokussiert auf Hauptinhalts-Tags.
    """

    time.sleep(random.uniform(1.5, 3.5))

    INVALID_CONTENT_PHRASES = [
        "bitte klicken sie hier", "nicht automatisch weitergeleitet",
        "click here if you are not redirected", "redirecting",
        "weiterleiten", "cookie", "404 not found"
    ]

    try:
        random_user_agent = random.choice(USER_AGENT_POOL)
        headers = {
            'User-Agent': random_user_agent,
            'Referer': 'https://duckduckgo.com/',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7'
        }

        proxies = {"http": current_proxy, "https": current_proxy} if current_proxy else None

        response = requests.get(url, headers=headers, timeout=20, proxies=proxies)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Entfernen irrelevanter HTML-Elemente (Navigation, Footer, etc.)
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            element.decompose()

        # VERBESSERTE EXTRAKTION: Nur Text aus Hauptinhalts-Tags (p, h1, h2, h3) holen
        content_tags = soup.find_all(['p', 'h1', 'h2', 'h3'])

        # Fallback auf Body, falls keine strukturierten Tags gefunden wurden
        if not content_tags:
            text = soup.body.get_text(separator=' ', strip=True)
        else:
            text = ' '.join(tag.get_text(separator=' ', strip=True) for tag in content_tags)

        cleaned_text = ' '.join(text.split())

        if len(cleaned_text) < 70:
            return f"[Konnte keinen substanziellen Text von dieser URL extrahieren - Länge: {len(cleaned_text)}]", False

        lower_text = cleaned_text.lower()
        if any(phrase in lower_text for phrase in INVALID_CONTENT_PHRASES):
            return f"[Ungültiger Inhalt erkannt: Weiterleitungs- oder Platzhalter-Text.]", False

        return cleaned_text, True

    except requests.exceptions.HTTPError as http_err:
        # 403 (Forbidden) wird hier abgefangen und als Fehler protokolliert
        error_msg = f"[Fehler: Die Seite {url} hat den Zugriff verweigert (Code: {http_err.response.status_code})]"
        return error_msg, (http_err.response.status_code != 403)

    except Exception as e:
        error_msg = f"[Fehler beim Laden von {url}: {type(e).__name__}]"
        return error_msg, False


def ki_wissensabruf_und_vergleich(anfrage, quelle_typ):
    """
    Führt eine Suche durch mit DDGS und nutzt Fallbacks.
    Maximale Wahrscheinlichkeit einer Antwort durch 4 Versuche und Whitelist-Fallback.
    """

    # quelle_typ ist nun fix
    quelle_typ = "Allgemeine Suche"

    MAX_RETRIES = 4
    suchanfrage_spezifisch = anfrage

    is_simple_question = anfrage.lower().startswith(("was ist", "was bedeutet", "wer ist", "def", "definition"))

    # Ausschluss von Blacklist-Domains direkt im Query
    domain_ausschlusse = " ".join([f"-site:{d}" for d in UNRELIABLE_DOMAINS if d not in ('youtube.com')])

    # --- 1. DDGS SUCH-STRATEGIEN ---
    suchanfrage_spezifisch = f"{anfrage} language:de {domain_ausschlusse}"

    # Keywords für irrelevante Themen ausschließen
    irrelevant_keywords = {'flüge', 'airfare', 'cheap', 'reisen', 'travel', 'flights', 'points'}

    error_log_full = []
    successful_result = None
    successful_content = None

    for retry_count in range(MAX_RETRIES):
        current_proxy = random.choice(PROXY_POOL) if PROXY_POOL and random.random() < 0.9 else None
        results = []

        if retry_count == 0:
            suchanfrage_effektiv = suchanfrage_spezifisch
            dienst_name = "DDGS (Spezifisch/Gefiltert)"
        elif retry_count < MAX_RETRIES - 1:
            suchanfrage_effektiv = f"{anfrage} {domain_ausschlusse}"
            dienst_name = "DDGS (Fallback/Allgemein)"
        else:
            if not is_simple_question:
                suchanfrage_effektiv = f"Was ist {anfrage}"
            else:
                suchanfrage_effektiv = anfrage
            dienst_name = "DDGS (Finaler, ungefilterter Versuch - Variiert)"

        # Längere Pausen
        if retry_count == 0:
            zufaellige_pause = random.uniform(5, 10)
        else:
            zufaellige_pause = random.uniform(3, 6)

        print(f"INFO: {dienst_name} Versuch ({retry_count + 1}). Warte {zufaellige_pause:.2f}s mit Proxy: {current_proxy if current_proxy else 'Kein Proxy'}")
        time.sleep(zufaellige_pause)

        try:
            with DDGS(timeout=20, proxy=current_proxy) as ddgs:
                results = list(ddgs.text(suchanfrage_effektiv, max_results=8))

            if not results:
                print(f"WARN: {dienst_name} lieferte keine Suchergebnisse.")
                continue

            error_log_retry = []

            for i, result in enumerate(results):
                first_url = result.get('href')
                first_title = result.get('title', '').lower()

                if not first_url or any(domain in first_url for domain in UNRELIABLE_DOMAINS) or any(kw in first_title for kw in irrelevant_keywords):
                    error_log_retry.append(f"Quelle #{i+1} ({first_url}): Ignoriert (Blacklist/Irrelevant).")
                    continue

                print(f"INFO: Versuche, Quelle #{i+1} zu laden: {first_url}")
                inhalt, success = get_text_from_url(first_url, current_proxy)

                if success:
                    successful_result = result
                    successful_content = inhalt
                    break
                else:
                    error_log_retry.append(f"Quelle #{i+1} ({first_url}): {inhalt}")

            error_log_full.extend(error_log_retry)

            if successful_result and successful_content:
                # Springe zur Ergebnisgenerierung, wenn erfolgreich
                break

        except Exception as e:
            error_message = f"FEHLER BEI INTERNET-SUCHE auf {dienst_name} (Versuch {retry_count + 1}): {type(e).__name__}: {e}"
            print(error_message)
            error_log_full.append(f"Suchdienst {dienst_name} ist fehlgeschlagen: {type(e).__name__}")

    # --- 2. WHITELIST FALLBACK (Versuch 5) ---

    if not successful_content:
        print("INFO: DDGS-Suche in allen 4 Versuchen fehlgeschlagen. Starte Whitelist-Fallback.")

        suchstring_query = anfrage.replace(" ", "+")

        for base_url in RELIABLE_URL_WHITELIST:

            # Wikipedia nutzt interne Suche
            if "wikipedia.org/" in base_url and "/wiki/" not in base_url:
                # Nutzt die interne Such-URL, die automatisch weiterleitet
                final_url = f"{base_url}w/index.php?search={suchstring_query}"
            # Spezialbehandlung für Spektrum-Lexikon
            elif "spektrum.de/lexikon" in base_url:
                final_url = f"{base_url}spektrum-a/lexikon-a/{suchstring_query}"
            # Spezialbehandlung für offizielle Python-Dokumentation
            elif "docs.python.org/3/" in base_url:
                final_url = f"{base_url}search.html?q={suchstring_query}"
            else:
                # Standard-Suche für offizielle Seiten
                final_url = f"{base_url}suche?q={suchstring_query}"

            print(f"INFO: Versuche, Whitelist-Quelle zu laden: {final_url}")

            time.sleep(random.uniform(2, 4))

            inhalt, success = get_text_from_url(final_url)

            if success:
                successful_result = {'title': f"Whitelist: {base_url.split('/')[2]}", 'href': final_url}
                successful_content = inhalt
                dienst_name = "Whitelist-Fallback"
                break

                # --- 3. ERGEBNIS GENERIEREN ---

    if successful_content:

        uebersetzter_inhalt = translate_to_german(successful_content)

        erkenntnis = f"Erkenntnis-Simulation (Quelle: {quelle_typ}, Dienst: {dienst_name}):\n\n"

        # LOGIK: WAHRSCHEINLICHSTE ANTWORT (Erster Abschnitt - bis zu 40 Zeilen)
        erkenntnis += f"--- WAHRSCHEINLICHSTE ANTWORT (Erster Abschnitt):\n\n"

        # 🟢 ANGEPASST: Maximal 2500 Zeichen für die vollen 40 Zeilen
        MAX_CHARS = 2500
        MAX_LINES = 40

        lines = []
        current_line = ""
        # Versucht, Absätze oder Sätze zu extrahieren, bis MAX_LINES oder MAX_CHARS erreicht sind
        for char in uebersetzter_inhalt:
            current_line += char
            if char in ('.', '!', '?') and len(current_line) > 50:
                lines.append(current_line.strip())
                current_line = ""
                if len(lines) >= MAX_LINES:
                    break
        if current_line and len(lines) < MAX_LINES:
            lines.append(current_line.strip())

        display_text = '\n'.join(lines)
        if len(display_text) > MAX_CHARS:
            # Stellt sicher, dass bei Überschreitung der 2500 Zeichen sauber am letzten Wort abgeschnitten wird
            display_text = display_text[:MAX_CHARS].rsplit(' ', 1)[0] + '...'


        # Fallback, falls die Logik zu kurz ist (z.B. nur ein Titel gefunden)
        if len(display_text) < 150 and len(uebersetzter_inhalt) > 150:
            display_text = uebersetzter_inhalt[:300].rsplit(' ', 1)[0] + '...'


        erkenntnis += f"**{display_text.strip()}**\n\n"

        # QUELLE
        erkenntnis += f"--- QUELLE DER ERKENNTNIS:\n"

        if dienst_name == "Whitelist-Fallback":
            quelle_titel = successful_result.get('title', 'Kein Titel').replace("Whitelist: ", "")
            erkenntnis += f"Quelle: **{quelle_titel}** \n"
        else:
            erkenntnis += f"Titel: {successful_result.get('title', 'Kein Titel')} \n"

        erkenntnis += f"URL: {successful_result.get('href')}\n\n"

        # Weitere gefundene Quellen (nur für DDGS-Fälle relevant)
        if dienst_name != "Whitelist-Fallback" and results:
            erkenntnis += "Weitere gefundene Quellen (ungeladen oder blockiert):\n"
            for res in results:
                if res != successful_result:
                    erkenntnis += f"- {res.get('title', 'Kein Titel')} ({res.get('href', 'Keine URL')})\n"

        save_to_db(anfrage, quelle_typ, erkenntnis)
        return erkenntnis

    # FINALER FEHLER NACH WHITELIST
    error_summary = "\n".join(error_log_full)
    return f"Keine Online-Dokumente extrahiert nach 4 DDGS-Versuchen UND dem Whitelist-Fallback.\n\n" \
           f"(Alle Quellen wurden blockiert, lieferten keinen substanziellen Text oder wurden als irrelevant übersprungen.)\n\n" \
           f"Fehler-Details (kumuliert):\n{error_summary}"

## 🖼️ GUI-LOGIK

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

        self.current_result_text = "" # Speichert das aktuelle Ergebnis

        if not initialize_db():
            messagebox.showerror("Datenbankfehler", "Konnte die SQLite-Datenbank nicht initialisieren. Programm wird beendet.")
            master.quit()
            return

        # Setze das Fenster in den Vollbildmodus
        master.attributes('-fullscreen', True)

        # Shortcut zum Beenden des Fullscreen-Modus
        master.bind('<Escape>', lambda e: master.attributes('-fullscreen', False))


        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(master, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)

        # 1. Eingabebereich
        ttk.Label(main_frame, text="Ihre Anfrage:", font=('Arial', 14, 'bold')).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self.anfrage_entry = ttk.Entry(main_frame, width=80, font=('Arial', 12))

        self.anfrage_entry.insert(0, "CO2 Definition")

        self.anfrage_entry.grid(row=1, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        self.anfrage_entry.focus()
        Tooltip(self.anfrage_entry, "Geben Sie eine Frage oder These ein.")

        # 2. Steuerung (Buttons)
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        button_frame.columnconfigure(0, weight=1)

        self.suchen_button = ttk.Button(button_frame, text="Suchen (Ctrl+S)", command=self.starte_suche_thread, style='TButton')
        self.suchen_button.grid(row=0, column=0, padx=5, sticky=(tk.W, tk.E))
        master.bind('<Control-s>', lambda event: self.starte_suche_thread())
        Tooltip(self.suchen_button, "Startet den KI-Vergleichsprozess. Das Ergebnis wird gespeichert.")

        # 3. Ausgabe-Bereich
        ttk.Label(main_frame, text="KI-Erkenntnis:", font=('Arial', 14, 'bold')).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(15, 5))

        text_frame = ttk.Frame(main_frame)
        text_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.ausgabe_text = tk.Text(text_frame, wrap=tk.WORD, state='disabled', font=('Arial', 11))
        self.ausgabe_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.ausgabe_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.ausgabe_text['yscrollcommand'] = scrollbar.set

    def starte_suche_thread(self):
        """Startet die Websuche in einem separaten Thread."""
        anfrage = self.anfrage_entry.get()
        if not anfrage:
            messagebox.showwarning("Eingabefehler", "Bitte geben Sie eine Anfrage ein.")
            return
        self.suchen_button.config(state='disabled')
        self.ausgabe_text.config(state='normal')
        self.ausgabe_text.delete(1.0, tk.END)
        self.ausgabe_text.insert(tk.END, "Suche, analysiere, **übersetze** und speichere... (Es werden bis zu 4 Versuche unternommen, gefolgt von einem Whitelist-Fallback)")
        self.ausgabe_text.config(state='disabled')

        threading.Thread(target=self.fuehre_suche_aus, args=(anfrage, "Allgemeine Suche",), daemon=True).start()

    def fuehre_suche_aus(self, anfrage, quelle):
        """Ruft die Backend-Logik auf."""
        ergebnis = ki_wissensabruf_und_vergleich(anfrage, quelle)
        self.master.after(0, self.aktualisiere_ausgabe, ergebnis, anfrage)

    def aktualisiere_ausgabe(self, ergebnis, anfrage):
        """Aktualisiert das Textfeld in der GUI."""
        self.current_result_text = ergebnis # Speichere das Ergebnis

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