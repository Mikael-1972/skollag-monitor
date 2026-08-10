import os
import json
import requests
from google import genai
from google.genai import types

# Fil för att spara ID på den senaste hanterade ändringen
STATE_FILE = "last_seen_change.txt"

def get_last_seen_id() -> str:
    """Hämtar ID för den senast behandlade ändringen från fil."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    return ""

def save_last_seen_id(doc_id: str):
    """Sparar ID för den senast behandlade ändringen."""
    with open(STATE_FILE, "w") as f:
        f.write(doc_id)

def fetch_skollagen_changes() -> dict:
    """
    Hämtar de senaste dokumenten/ändringarna kopplade till Skollagen (2010:800)
    från Riksdagens öppna API.
    """
    # Sök efter dokument som berör SFS 2010:800
    url = "https://data.riksdagen.se/dokumentlista/?sok=2010:800&doktyp=sfs&utformat=json&sort=datum&sortorder=desc"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Hämta det senaste dokumentet i listan
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

def send_notification(subject: str, body: str):
    """
    Simulerar utskick av notis (kan bytas ut mot SMTP för e-post eller Webhook för Slack/Discord).
    """
    print("\n=" * 50)
    print(f"NOTISERINGS-LARM: {subject}")
    print("=" * 50)
    print(body)
    print("=" * 50 + "\n")

# Main execution
def run_monitor():
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    last_seen_id = get_last_seen_id()
    latest_change = fetch_skollagen_changes()

    if not latest_change:
        print("Kunde inte hämta data eller inga ändringar hittades.")
        return

    # Om det finns en ny ändring som vi inte har behandlat tidigare
    if latest_change["id"] != last_seen_id:
        print(f"Ny ändring upptäckt! ID: {latest_change['id']}")

        # Be Gemini analysera uppdateringen
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

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="Du är en juridisk expert på svensk skolrätt och pedagogisk lagstiftning."
            )
        )

        # Skicka notis
        subject = f"Uppdatering i Skollagen: {latest_change['titel']}"
        body = f"{response.text}\n\nLäs mer i sin helhet här: {latest_change['url']}"
        send_notification(subject, body)

        # Uppdatera minnet så vi inte larmar om samma ändring igen
        save_last_seen_id(latest_change["id"])
    else:
        print("Inga nya ändringar i Skollagen sedan förra kontrollen.")

if __name__ == "__main__":
    run_monitor()
