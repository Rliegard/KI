###########################################################################################
# PROJEKT: Wissens-KI KI.M8  (FEATURE: Verlauf und Cache-Anzeige)
# DATEI:   wissens_ki_m8.py
#
# BESCHREIBUNG:
# Diese Version fügt eine GUI-Funktion zur Anzeige des gespeicherten Verlaufs
# (Cache) hinzu, um die Funktionalität der SQLite-Datenbank abzuschließen.
# Die Anti-Block-Logik, der Quellenvergleich und die stabile Übersetzung
# (deep-translator) bleiben erhalten.
#
# NEUE FUNKTIONEN:
# 1. Verlauf anzeigen Button (Ctrl+H): Öffnet ein separates Fenster.
# 2. Klasse VerlaufAnzeigeFenster: Stellt alle Cache-Einträge in einer Treeview dar.
#
# AUTOR: Rainer Liegard
# Datum: 06.11.2025
###########################################################################################

import tkinter as tk
from tkinter import ttk, messagebox, Toplevel, scrolledtext
import threading
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
import time
import random
import sqlite3
# NEU: Import der stabileren Übersetzer-Bibliothek
from deep_translator import GoogleTranslator
from thefuzz import process, fuzz

# --- GLOBALE KONSTANTEN UND LISTEN ---
DB_NAME = "wissens_ki_cache.db"
MAX_RETRIES = 2
MAX_CHARS = 5000
MAX_LINES = 50
SIMILARITY_CUTOFF = 50
MIN_TEXT_LENGTH = 150
TRANSLATION_BLOCK_SIZE = 4500

# Liste der Domains, die bekanntermaßen unstrukturierten Text liefern (Blacklist)
UNRELIABLE_DOMAINS = [
    'baidu.com', 'quora.com', 'pinterest.com', 'twitter.com',
    'vk.com', 'reddit.com/r/', 'youtube.com', 'amazon.com', 'aliexpress.com',
]

# Erweiterte Liste der User-Agents zur besseren Verschleierung
USER_AGENT_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36',
]

# Statische Liste zuverlässiger URLs (WHITELIST)
RELIABLE_URL_WHITELIST = [
    "https://de.wikipedia.org/", "https://www.bmbf.de/", "https://www.destatis.de/",
    "https://www.spektrum.de/lexikon/", "https://www.bpb.de/", "https://www.bundestag.de/",
    "https://www.umweltbundesamt.de/", "https://www.mpg.de/", "https://www.helmholtz.de/",
    "https://www.scinexx.de/", "https://www.leibniz-gemeinschaft.de/", "https://en.wikipedia.org/",
    "https://www.nasa.gov/", "https://www.who.int/", "https://www.un.org/en/",
    "https://www.nature.com/", "https://www.sciencemag.org/", "https://www.science.org/",
    "https://www.nih.gov/", "https://www.usgs.gov/", "https://www.journals.elsevier.com/",
    "https://www.sciencedirect.com/", "https://www.plos.org/", "https://www.epa.gov/",
    "https://www.eia.gov/", "https://www.esa.int/", "https://www.cern.ch/",
    "https://docs.python.org/3/",
]

# PROXY-POOL (Implementierte IP-Verschleierung - WICHTIG: Ersetzen Sie diese Liste regelmäßig mit funktionierenden, aktuellen Proxys)
PROXY_POOL = [
    None, # 1. Direkte Verbindung (Standard-Fallback)
    'http://150.242.12.169:80',    # Elite Proxy, Indien, unterstützt HTTPS
    'http://152.70.137.18:8888',   # Anonymous, USA, unterstützt HTTPS
    'http://211.230.49.122:3128',  # Anonymous, Südkorea, unterstützt HTTPS
    'http://217.138.18.75:8080',   # Elite Proxy, UK, unterstützt HTTPS
    'http://5.252.33.13:2025',    # Elite Proxy, Slowakei, unterstützt HTTPS
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
        # Stellen Sie sicher, dass der Text vor dem Speichern auf MAX_CHARS begrenzt wird
        text_to_save = ergebnis_text[:MAX_CHARS]
        cursor.execute("INSERT INTO anfragen_cache (anfrage, quelle_typ, ergebnis_text) VALUES (?, ?, ?)",
                       (anfrage, quelle_typ, text_to_save))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Fehler beim Speichern in die Datenbank: {e}")
        return False

def load_all_cache_data():
    """Lädt alle Daten aus dem Cache."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Spalten: id, anfrage, quelle_typ, timestamp, ergebnis_text
        cursor.execute("SELECT id, anfrage, quelle_typ, timestamp, ergebnis_text FROM anfragen_cache ORDER BY id DESC")
        data = cursor.fetchall()
        conn.close()
        return data
    except Exception as e:
        print(f"Fehler beim Laden der Cache-Daten: {e}")
        return []

def get_similar_cached_queries(anfrage):
    """Sucht im Cache nach Anfragen, die der aktuellen Anfrage ähnlich sind."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT anfrage FROM anfragen_cache ORDER BY timestamp DESC")
        cached_queries = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not cached_queries: return []
        # Verwendet thefuzz zur Ähnlichkeitsprüfung
        matches = process.extractBests(
            anfrage, list(set(cached_queries)), scorer=fuzz.token_set_ratio,
            score_cutoff=SIMILARITY_CUTOFF, limit=5
        )
        return [f"{query} (Ähnlichkeit: {score}%)" for query, score in matches]
    except Exception as e:
        print(f"Fehler beim Abrufen ähnlicher Anfragen: {e}")
        return []

def translate_to_german(text):
    """
    Übersetzt den gegebenen Text ins Deutsche mithilfe von deep_translator.
    """
    if not text:
        return ""

    translator = GoogleTranslator(source='auto', target='de')
    text_blocks = []
    current_block = ""

    # Einfache Satzzerlegung für Übersetzungsblöcke
    sentences = [s.strip() for s in text.replace('\n', ' ').split('. ') if s.strip()]

    for sentence in sentences:
        full_sentence = sentence + ". "
        if len(current_block) + len(full_sentence) <= TRANSLATION_BLOCK_SIZE:
            current_block += full_sentence
        else:
            if current_block: text_blocks.append(current_block)
            current_block = full_sentence
    if current_block: text_blocks.append(current_block)

    translated_text = []

    print(f"INFO: Starte robuste Übersetzung von {len(text_blocks)} Textblöcken...")

    for i, block in enumerate(text_blocks):
        try:
            translation = translator.translate(block)
            translated_text.append(translation)
            if len(text_blocks) > 1:
                time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            print(f"[Übersetzungsfehler Block {i+1} - {type(e).__name__}: Verwende Originaltext.]")
            translated_text.append(block)
            time.sleep(random.uniform(0.5, 1.0))

    final_translation = "".join(translated_text)
    if len(final_translation) > 0:
        return final_translation
    else:
        return f"[Übersetzungsfehler: Der gesamte Text konnte nicht übersetzt werden.]\n\nOriginal:\n{text}"

def summarize_multiple_sources(sources_data, anfrage):
    """
    Vergleicht und fasst Texte aus mehreren Whitelist-Quellen zusammen.
    """
    combined_summary = []
    source_info = "\n--- VERGLEICH DER WHITELIST-QUELLEN (Analysiert) ---\n"

    for i, data in enumerate(sources_data):
        title = data['title']
        translated_text = data['text']
        url = data['href']

        source_info += f"Quelle #{i+1}: **{title.replace('Whitelist: ', '')}**\nURL: {url}\n"

        sentences = [s.strip() for s in translated_text.split('.') if s.strip()]
        relevant_sentences = []
        for sentence in sentences:
            relevance_score = len(sentence) / 100 # Basisscore
            for word in anfrage.lower().split():
                if word in sentence.lower():
                    relevance_score += 1.0
            relevant_sentences.append((sentence, relevance_score))

        relevant_sentences.sort(key=lambda x: x[1], reverse=True)
        top_sentences = relevant_sentences[:5]

        for sentence, score in top_sentences:
            combined_summary.append({
                'text': f"[{i+1}] {sentence}.",
                'score': score,
                'source': title
            })

    combined_summary.sort(key=lambda x: x['score'], reverse=True)
    final_summary_lines = []
    unique_sentences = set()

    for item in combined_summary:
        sentence_without_tag = item['text'][4:]
        if sentence_without_tag not in unique_sentences:
            final_summary_lines.append(item['text'])
            unique_sentences.add(sentence_without_tag)

        if len(final_summary_lines) >= MAX_LINES:
            break

    final_text = ' '.join(final_summary_lines)

    if len(final_text) > MAX_CHARS:
        final_text = final_text[:MAX_CHARS].rsplit('.', 1)[0] + '... (Gekürzt auf 5000 Zeichen)'

    return final_text, source_info


## 🔍 BACKEND-LOGIK (Web-Suche und Scraping)

def get_text_from_url(url, current_proxy=None):
    """
    Holt den reinen Text von einer URL, mit robuster Fallback-Logik.
    """

    time.sleep(random.uniform(1.5, 3.5))

    INVALID_CONTENT_PHRASES = [
        "bitte klicken sie hier", "nicht automatisch weitergeleitet",
        "click here if you are not redirected", "redirecting",
        "weiterleiten", "cookie", "404 not found", "error page",
        "access denied", "robot check"
    ]

    try:
        random_user_agent = random.choice(USER_AGENT_POOL)
        headers = {
            'User-Agent': random_user_agent,
            'Referer': 'https://duckduckgo.com/',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        }

        proxies = {"http": current_proxy, "https": current_proxy} if current_proxy else None

        response = requests.get(url, headers=headers, timeout=20, proxies=proxies)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "meta", "link"]):
            element.decompose()

        content_tags = soup.find_all(['p', 'h1', 'h2', 'h3', 'li'])
        if content_tags:
            text = ' '.join(tag.get_text(separator=' ', strip=True) for tag in content_tags)
        else:
            main_content = soup.find(['main', 'article'])
            if main_content:
                text = main_content.get_text(separator=' ', strip=True)
            else:
                text = soup.body.get_text(separator=' ', strip=True)

        cleaned_text = ' '.join(text.split())

        if len(cleaned_text) < MIN_TEXT_LENGTH:
            return f"[Konnte keinen substanziellen Text von dieser URL extrahieren - Länge: {len(cleaned_text)}]", False

        lower_text = cleaned_text.lower()
        if any(phrase in lower_text for phrase in INVALID_CONTENT_PHRASES):
            return f"[Ungültiger Inhalt erkannt: Weiterleitungs- oder Platzhalter-Text.]", False

        return cleaned_text, True

    except requests.exceptions.HTTPError as http_err:
        error_msg = f"[Fehler: Die Seite {url} hat den Zugriff verweigert (Code: {http_err.response.status_code})]"
        return error_msg, (http_err.response.status_code not in [403, 404])

    except Exception as e:
        error_msg = f"[Fehler beim Laden von {url}: {type(e).__name__}]"
        return error_msg, False


def ki_wissensabruf_und_vergleich(anfrage, quelle_typ, stop_search_flag):
    """
    Führt eine Suche durch mit 1x DDGS und den anschließenden Quellenvergleich.
    """

    quelle_typ = "Allgemeine Suche"
    domain_ausschlusse = " ".join([f"-site:{d}" for d in UNRELIABLE_DOMAINS if d not in ('youtube.com')])
    suchanfrage_effektiv = f"{anfrage} language:de {domain_ausschlusse}"
    dienst_name_current = "DDGS (Spezifisch/Gefiltert - V1)"
    irrelevant_keywords = {'flüge', 'airfare', 'cheap', 'reisen', 'travel', 'flights', 'points'}

    error_log_full = []
    successful_content = None
    successful_result = None
    dienst_name = ""
    results = []
    quelle_zusatz = ""

    # 1. DDGS SUCH-STRATEGIEN (MAX_RETRIES)
    for retry_count in range(MAX_RETRIES):
        if stop_search_flag.is_set():
            return "Suche durch den Benutzer abgebrochen.", "Abbruch"

        effective_proxy_pool = [p for p in PROXY_POOL if p is not None]
        if effective_proxy_pool and random.random() < 0.75:
            current_proxy = random.choice(effective_proxy_pool)
        else:
            current_proxy = None

        zufaellige_pause = random.uniform(5, 10)
        print(f"INFO: {dienst_name_current} Versuch ({retry_count + 1}). Warte {zufaellige_pause:.2f}s mit Proxy: {current_proxy if current_proxy else 'Kein Proxy'}")
        time.sleep(zufaellige_pause)

        try:
            with DDGS(timeout=20, proxy=current_proxy) as ddgs:
                results = list(ddgs.text(suchanfrage_effektiv, max_results=8))

            if not results: continue
            error_log_retry = []

            for i, result in enumerate(results):
                if stop_search_flag.is_set(): return "Suche durch den Benutzer abgebrochen.", "Abbruch"
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
                    dienst_name = dienst_name_current
                    break
                else:
                    error_log_retry.append(f"Quelle #{i+1} ({first_url}): {inhalt}")

            error_log_full.extend(error_log_retry)
            if successful_result and successful_content: break

        except Exception as e:
            error_log_full.append(f"Suchdienst {dienst_name_current} ist fehlgeschlagen: {type(e).__name__} (Möglicherweise IP-Blockade!)")


    # 2. WHITELIST FALLBACK MIT QUELLENVERGLEICH
    whitelist_results = []
    if not successful_content:
        print("INFO: DDGS-Suche fehlgeschlagen. Starte Whitelist-Fallback mit Quellenvergleich.")
        suchstring_query = anfrage.replace(" ", "+")
        effective_proxy_pool = [p for p in PROXY_POOL if p is not None]

        for base_url in RELIABLE_URL_WHITELIST:
            if stop_search_flag.is_set(): return "Suche durch den Benutzer abgebrochen.", "Abbruch"

            current_proxy = random.choice(effective_proxy_pool) if effective_proxy_pool and random.random() < 0.75 else None

            # URL-Erstellung (unverändert)
            final_url = ""
            domain_name = base_url.split('/')[2]
            if "wikipedia.org/" in base_url and "/wiki/" not in base_url:
                final_url = f"{base_url}w/index.php?search={suchstring_query}"
            elif "spektrum.de/lexikon" in base_url:
                final_url = f"{base_url}{suchstring_query}"
            elif "docs.python.org/3/" in base_url:
                final_url = f"{base_url}search.html?q={suchstring_query}"
            elif domain_name in ["www.nasa.gov", "www.nih.gov", "www.epa.gov", "www.eia.gov", "www.usgs.gov", "www.nature.com", "www.sciencemag.org", "www.science.org"]:
                final_url = f"{base_url}search?q={suchstring_query}"
            elif domain_name == "www.sciencedirect.com":
                final_url = f"{base_url}search?qs={suchstring_query}"
            else:
                final_url = f"{base_url}suche?q={suchstring_query}"

            print(f"INFO: Versuche, Whitelist-Quelle zu laden: {final_url}")
            time.sleep(random.uniform(1.0, 2.5))
            inhalt, success = get_text_from_url(final_url, current_proxy)

            if success:
                whitelist_results.append({
                    'title': f"Whitelist: {base_url.split('/')[2]}",
                    'href': final_url,
                    'text_original': inhalt
                })

        if whitelist_results:
            dienst_name = "Whitelist-Quellenvergleich"
            for item in whitelist_results:
                if stop_search_flag.is_set(): return "Suche durch den Benutzer abgebrochen.", "Abbruch"
                item['text'] = translate_to_german(item['text_original'])

            combined_content, source_info = summarize_multiple_sources(whitelist_results, anfrage)
            successful_result = {'title': 'Mehrere Whitelist-Quellen', 'href': 'Zusammenfassung'}
            successful_content = combined_content
            quelle_zusatz = source_info

    # --- 3. ERGEBNIS GENERIEREN ---
    if successful_content:
        if successful_content == "Abbruch":
            return "Suche durch den Benutzer abgebrochen."

        erkenntnis = f"Erkenntnis-Simulation (Quelle: {quelle_typ}, Dienst: {dienst_name}):\n\n"

        if dienst_name != "Whitelist-Quellenvergleich":
            uebersetzter_inhalt = translate_to_german(successful_content)
            if uebersetzter_inhalt.startswith("[Übersetzungsfehler:"):
                erkenntnis += "[INFO: Übersetzung fehlgeschlagen. Originaltext wird verwendet.]\n"
                display_text = successful_content
            else:
                display_text = uebersetzter_inhalt

            erkenntnis += f"--- WAHRSCHEINLICHSTE ANTWORT:\n\n"

            if len(display_text) > MAX_CHARS:
                display_text = display_text[:MAX_CHARS].rsplit('.', 1)[0] + '... (Gekürzt auf 5000 Zeichen)'

            erkenntnis += f"**{display_text.strip()}**\n\n"
            erkenntnis += f"--- QUELLE DER ERKENNTNIS:\n"
            erkenntnis += f"Titel: {successful_result.get('title', 'Kein Titel')} \n"
            erkenntnis += f"URL: {successful_result.get('href')}\n\n"

            if results:
                erkenntnis += "Weitere gefundene Quellen (ungeladen oder blockiert):\n"
                for res in results:
                    if res != successful_result:
                        erkenntnis += f"- {res.get('title', 'Kein Titel')} ({res.get('href', 'Keine URL')})\n"
        else:
            erkenntnis += f"--- VERGLEICHENDE ZUSAMMENFASSUNG (KI-Analyse):\n\n"
            erkenntnis += f"**{successful_content}**\n\n"
            erkenntnis += quelle_zusatz

        save_to_db(anfrage, dienst_name, erkenntnis)
        return erkenntnis

    # --- 4. FINALER FEHLER NACH WHITELIST + FUZZY-MATCHING ---

    error_summary = "\n".join(error_log_full)
    similar_queries = get_similar_cached_queries(anfrage)

    ip_hint = "\n\n*** WICHTIGER HINWEIS: ***\nDie Proxys wurden in den Code integriert. Wenn Fehler weiterhin auftreten, sind die kostenlosen Proxys wahrscheinlich bereits überlastet oder blockiert. Sie müssen dann **neue Proxys** in der Liste 'PROXY_POOL' eintragen."

    if successful_content == "Suche durch den Benutzer abgebrochen." or successful_content == "Abbruch":
        error_output = "Suche wurde erfolgreich durch den Benutzer abgebrochen."
    else:
        error_output = f"Keine Online-Dokumente extrahiert nach {MAX_RETRIES} DDGS-Versuchen UND dem Whitelist-Fallback (Quellenvergleich). \n\n" \
                       f"(Alle Quellen wurden blockiert, lieferten keinen substanziellen Text oder wurden als irrelevant/zu kurz übersprungen. Mindestlänge: {MIN_TEXT_LENGTH} Zeichen.)\n\n" \
                       f"Fehler-Details (kumuliert):\n{error_summary}\n" + ip_hint + "\n\n"

        if similar_queries:
            error_output += f"--- ÄHNLICHE ARTIKEL IM CACHE (Ähnlichkeit > {SIMILARITY_CUTOFF}%):\n"
            for query in similar_queries:
                error_output += f"- {query}\n"
        else:
            error_output += f"--- KEINE ÄHNLICHEN ARTIKEL im Cache (Ähnlichkeit > {SIMILARITY_CUTOFF}%).\n"

    return error_output

# --- NEUE KLASSEN FÜR DIE CACHE-ANZEIGE ---

class VerlaufAnzeigeFenster:
    """Zeigt alle gespeicherten Anfragen und Ergebnisse in einer Treeview an."""
    def __init__(self, master):
        self.top = Toplevel(master)
        self.top.title("Wissens-KI Cache-Verlauf")
        self.top.geometry("1200x800")
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self.top, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Treeview zur Anzeige der Cache-Daten
        self.tree = ttk.Treeview(main_frame, columns=('ID', 'Anfrage', 'Typ', 'Zeitstempel'), show='headings')
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 20))

        # Konfiguration der Spalten
        self.tree.heading('ID', text='ID', anchor=tk.CENTER)
        self.tree.heading('Anfrage', text='Anfrage', anchor=tk.W)
        self.tree.heading('Typ', text='Quelle Typ', anchor=tk.W)
        self.tree.heading('Zeitstempel', text='Zeitstempel', anchor=tk.W)

        self.tree.column('ID', width=50, stretch=tk.NO, anchor=tk.CENTER)
        self.tree.column('Anfrage', width=450)
        self.tree.column('Typ', width=150)
        self.tree.column('Zeitstempel', width=200)

        # Scrollbar
        vsb = ttk.Scrollbar(main_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=vsb.set)

        # Detailbereich (Textfeld für das vollständige Ergebnis)
        ttk.Label(main_frame, text="Vollständiges Ergebnis:", font=('Arial', 11, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=(10, 5))
        self.detail_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=15, font=('Arial', 10), state='disabled')
        self.detail_text.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E))

        # Event-Bindung für Klick auf Treeview
        self.tree.bind('<<TreeviewSelect>>', self.zeige_details)

        self.lade_daten()

    def lade_daten(self):
        """Lädt Daten aus der DB und fügt sie in die Treeview ein."""
        for i in self.tree.get_children():
            self.tree.delete(i)

        data = load_all_cache_data()
        self.cache_data = {row[0]: row[4] for row in data} # Speichert ID -> Volltext

        for row in data:
            # Fügt nur ID, Anfrage, Typ und Zeitstempel in die Treeview ein
            self.tree.insert('', tk.END, iid=row[0], values=(row[0], row[1], row[2], row[3]))

    def zeige_details(self, event):
        """Zeigt den vollständigen Text des ausgewählten Eintrags im Detailbereich an."""
        selected_item = self.tree.focus()
        if not selected_item: return

        # Holt die ID (die iid ist die Datenbank-ID)
        db_id = int(self.tree.item(selected_item, 'iid'))
        full_text = self.cache_data.get(db_id, "Fehler: Ergebnis konnte nicht aus dem Cache abgerufen werden.")

        self.detail_text.config(state='normal')
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.insert(tk.END, full_text)
        self.detail_text.config(state='disabled')


class Tooltip:
    """Erstellt einen Tooltip für ein Tkinter-Widget."""
    # (Unverändert übernommen)
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.close)

    def enter(self, event=None): self.schedule()
    def schedule(self):
        self.unschedule()
        self.tw_id = self.widget.after(500, self.show)

    def unschedule(self):
        if hasattr(self, 'tw_id') and self.tw_id:
            self.widget.after_cancel(self.tw_id)
            self.tw_id = None

    def show(self):
        if self.tw: return
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
        if self.tw:
            self.tw.destroy()
            self.tw = None


class WissensKI_GUI:
    """Die Haupt-GUI-Klasse für die Anwendung."""
    def __init__(self, master):
        self.master = master
        master.title("Wissens-KI (Prototyp mit Anti-Block-Logik)")

        self.current_result_text = ""
        self.current_anfrage = ""
        self.stop_search_flag = threading.Event()
        self.search_running = False

        if not initialize_db():
            messagebox.showerror("Datenbankfehler", "Konnte die SQLite-Datenbank nicht initialisieren. Programm wird beendet.")
            master.quit()
            return

        master.attributes('-fullscreen', True)
        master.bind('<Escape>', lambda e: master.attributes('-fullscreen', False))
        master.bind('<Control-q>', lambda e: master.quit())

        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(master, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        # Beenden-Button
        top_right_frame = ttk.Frame(main_frame)
        top_right_frame.grid(row=0, column=1, sticky=tk.NE, padx=5, pady=5)
        self.exit_button = ttk.Button(top_right_frame, text="Beenden (Ctrl+Q / Esc)", command=master.quit, style='TButton')
        self.exit_button.pack(side=tk.RIGHT)
        Tooltip(self.exit_button, "Beendet die Anwendung.")


        # 1. Eingabebereich
        ttk.Label(main_frame, text="Ihre Anfrage:", font=('Arial', 14, 'bold')).grid(row=1, column=0, columnspan=2, sticky=tk.W)
        self.anfrage_entry = ttk.Entry(main_frame, width=80, font=('Arial', 12))
        self.anfrage_entry.insert(0, "Adolf Hitler")
        self.anfrage_entry.grid(row=2, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        self.anfrage_entry.focus()
        Tooltip(self.anfrage_entry, "Geben Sie eine Frage oder These ein.")

        # 2. Steuerung (Buttons)
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)
        button_frame.columnconfigure(3, weight=1) # Platz für 4 Buttons

        self.suchen_button = ttk.Button(button_frame, text="Suchen (Ctrl+S)", command=self.starte_suche_thread, style='TButton')
        self.suchen_button.grid(row=0, column=0, padx=5, sticky=(tk.W, tk.E))
        master.bind('<Control-s>', lambda event: self.starte_suche_thread())
        Tooltip(self.suchen_button, "Startet den KI-Vergleichsprozess (dauert ca. 30-60s).")

        self.abbrechen_button = ttk.Button(button_frame, text="Abbrechen (Ctrl+A)", command=self.brich_suche_ab, state='disabled', style='TButton')
        self.abbrechen_button.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        master.bind('<Control-a>', lambda event: self.brich_suche_ab())
        Tooltip(self.abbrechen_button, "Bricht die aktuell laufende Suchanfrage ab.")

        # NEU: VERLAUF-BUTTON
        self.verlauf_button = ttk.Button(button_frame, text="Verlauf anzeigen (Ctrl+H)", command=self.oeffne_verlauf, style='Accent.TButton')
        self.verlauf_button.grid(row=0, column=2, padx=5, sticky=(tk.W, tk.E))
        master.bind('<Control-h>', lambda event: self.oeffne_verlauf())
        Tooltip(self.verlauf_button, "Zeigt alle im Cache gespeicherten Anfragen und Ergebnisse an.")

        self.speichern_button = ttk.Button(button_frame, text="Ergebnis Speichern", command=self.speichere_ergebnis, state='disabled', style='TButton')
        self.speichern_button.grid(row=0, column=3, padx=5, sticky=(tk.W, tk.E))
        Tooltip(self.speichern_button, "Speichert das aktuell angezeigte Ergebnis manuell in der Datenbank.")


        # 3. Ausgabe-Bereich
        ttk.Label(main_frame, text="KI-Erkenntnis:", font=('Arial', 14, 'bold')).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(15, 5))

        text_frame = ttk.Frame(main_frame)
        text_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.ausgabe_text = tk.Text(text_frame, wrap=tk.WORD, state='disabled', font=('Arial', 11))
        self.ausgabe_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.ausgabe_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.ausgabe_text['yscrollcommand'] = scrollbar.set

    def oeffne_verlauf(self, event=None):
        """Öffnet das separate Fenster zur Anzeige des Cache-Verlaufs."""
        VerlaufAnzeigeFenster(self.master)

    def speichere_ergebnis(self):
        """Speichert das aktuelle Ergebnis manuell in die Datenbank."""
        if self.current_result_text and not self.current_result_text.startswith("Keine Online-Dokumente"):
            success = save_to_db(self.current_anfrage, "Manuell gespeichert", self.current_result_text)
            if success:
                messagebox.showinfo("Speichern Erfolgreich", "Das aktuelle Ergebnis wurde erfolgreich im Cache gespeichert.")
            else:
                messagebox.showerror("Speichern Fehlgeschlagen", "Fehler beim Speichern in die Datenbank.")
        else:
            messagebox.showwarning("Kein Ergebnis", "Es kann kein leeres oder fehlerhaftes Ergebnis gespeichert werden.")

    def brich_suche_ab(self, event=None):
        """Setzt das Flag, um den laufenden Such-Thread zu beenden."""
        if self.search_running:
            self.stop_search_flag.set()
            self.abbrechen_button.config(state='disabled')

            self.ausgabe_text.config(state='normal')
            self.ausgabe_text.insert(tk.END, "\n\n--- ABBRUCH-SIGNAL GESENDET. Warte auf thread-sichere Beendigung... ---\n")
            self.ausgabe_text.config(state='disabled')
        else:
            messagebox.showinfo("Status", "Derzeit läuft keine Suche.")


    def starte_suche_thread(self, event=None):
        """Startet die Websuche in einem separaten Thread."""
        anfrage = self.anfrage_entry.get()
        if not anfrage or self.search_running:
            return

        self.current_anfrage = anfrage
        self.search_running = True
        self.stop_search_flag.clear()

        # GUI-Elemente aktualisieren
        self.suchen_button.config(state='disabled')
        self.speichern_button.config(state='disabled')
        self.verlauf_button.config(state='disabled')
        self.abbrechen_button.config(state='normal')

        self.ausgabe_text.config(state='normal')
        self.ausgabe_text.delete(1.0, tk.END)
        self.ausgabe_text.insert(tk.END, f"Suche, analysiere, **übersetze** und speichere... (2 DDGS-Versuche, dann **robuster Whitelist-Vergleich** mit verbesserter Anti-Detection-Logik. Max. {MAX_CHARS} Zeichen).")
        self.ausgabe_text.config(state='disabled')

        threading.Thread(target=self.fuehre_suche_aus, args=(anfrage, "Allgemeine Suche", self.stop_search_flag,), daemon=True).start()

    def fuehre_suche_aus(self, anfrage, quelle, stop_search_flag):
        """Ruft die Backend-Logik auf."""
        ergebnis = ki_wissensabruf_und_vergleich(anfrage, quelle, stop_search_flag)
        self.master.after(0, self.aktualisiere_ausgabe, ergebnis, anfrage)

    def aktualisiere_ausgabe(self, ergebnis, anfrage):
        """Aktualisiert das Textfeld in der GUI."""
        self.current_result_text = ergebnis
        self.search_running = False

        self.ausgabe_text.config(state='normal')
        self.ausgabe_text.delete(1.0, tk.END)
        self.ausgabe_text.insert(tk.END, ergebnis)
        self.ausgabe_text.config(state='disabled')

        # GUI-Elemente zurücksetzen
        self.suchen_button.config(state='normal')
        self.abbrechen_button.config(state='disabled')
        self.verlauf_button.config(state='normal')

        if not ergebnis.startswith("Keine Online-Dokumente") and not ergebnis.startswith("Suche wurde"):
            self.speichern_button.config(state='normal')
        else:
            self.speichern_button.config(state='disabled')


## 🚀 ANWENDUNG STARTEN

if __name__ == "__main__":
    root = tk.Tk()
    app = WissensKI_GUI(root)
    root.mainloop()