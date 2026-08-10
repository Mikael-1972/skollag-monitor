import os
import json
import time
import requests
import resend
from google import genai
from google.genai import types

STATE_FILE = "last_seen_change.txt"
RECIPIENT_EMAIL = "mian72@gmail.com"

def get_last_seen_id() -> str:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    return ""

def save_last_seen_id(doc_id: str):
    with open(STATE_FILE, "w") as f:
        f.write(doc_id)

def fetch_skollagen_changes() -> dict:
    url = "https://data.riksdagen.se/dokumentlista/?sok=2010:800&doktyp=sfs&utformat=json&sort=datum&sortorder=desc"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        documents = data.get("dokumentlista", {}).get("dokument", [])
        if documents:
            latest_doc = documents[0]
            return {
                "id": latest_doc.get("id"),
                "titel": latest_doc.get("titel"),
                "datum": latest_doc.get("datum"),
                "summary": latest_doc.get("summary", ""),
                "url": f"https://www.riksdagen.se/sv/dokument-och-lagar/dokument/{latest_doc.get('dok_id')}"
            }
    except Exception as e:
        print(f"Fel vid hämtning från Riksdagen: {e}")
    return {}

def send_email_notification(subject: str, body_text: str):
    resend_api_key = os.environ.get("RESEND_API_KEY")
    
    if not resend_api_key:
        print("Varning: RESEND_API_KEY saknas i secrets.")
        return

    resend.api_key = resend_api_key
    html_content = body_text.replace("\n", "<br>")

    try:
        r = resend.Emails.send({
            "from": "SkollagAgent <onboarding@resend.dev>",
            "to": RECIPIENT_EMAIL,
            "subject": subject,
            "html": f"<h2>Ny ändring i Skollagen registrerad</h2><p>{html_content}</p>"
        })
        print(f"E-post skickat framgångsrikt till {RECIPIENT_EMAIL}!")
    except Exception as e:
        print(f"E-POSTFEL: Kunde inte skicka mejl via Resend: {e}")

def run_monitor():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("FEL: GEMINI_API_KEY saknas!")
        return

    client = genai.Client(api_key=api_key)
    
    last_seen_id = get_last_seen_id()
    latest_change = fetch_skollagen_changes()

    if not latest_change:
        print("Kunde inte hämta data från Riksdagen.")
        return

    if latest_change["id"] != last_seen_id:
        print(f"Ny ändring upptäckt! ID: {latest_change['id']}")

        prompt = f"""
        En ny ändring eller tillägg har registrerats gällande Skollagen (2010:800).
        
        Titel: {latest_change['titel']}
        Datum: {latest_change['datum']}
        Utdrag/Sammanfattning: {latest_change['summary']}
        Länk: {latest_change['url']}
        
        Gör följande:
        1. Sammanfatta vad denna ändring innebär i 3-4 korta punkter.
        2. Förklara vilka som primärt påverkas (t.ex. rektorer, lärare, elever, huvudmän).
        3. Håll språket professionellt, tydligt och lättillgängligt.
        """

        analysis_text = ""
        # Försök 1: Anropa Gemini
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="Du är en juridisk expert på svensk skolrätt och pedagogisk lagstiftning."
                )
            )
            analysis_text = response.text
        except Exception as e:
            print(f"Svarade med fel första gången: {e}")
            print("Väntar 40 sekunder och försöker igen...")
            time.sleep(40)
            
            # Försök 2: Kör igen efter paus
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="Du är en juridisk expert på svensk skolrätt och pedagogisk lagstiftning."
                    )
                )
                analysis_text = response.text
            except Exception as e2:
                print(f"Kunde inte nå Gemini: {e2}")
                analysis_text = f"Ny ändring registrerad i Skollagen: {latest_change['titel']}.\n(AI-analysen kunde inte slutföras på grund av tillfällig kvotbegränsning, men du kan läsa ändringen på länken nedan)."

        subject = f"Lagändring Skollagen: {latest_change['titel']}"
        body = f"{analysis_text}\n\nLäs mer i sin helhet här: {latest_change['url']}"
        
        # Skicka e-post
        send_email_notification(subject, body)
        
        # Spara senast behandlade ID så att samma ändring inte skickas igen
        save_last_seen_id(latest_change["id"])
    else:
        print("Inga nya ändringar i Skollagen sedan förra kontrollen.")

if __name__ == "__main__":
    run_monitor()
