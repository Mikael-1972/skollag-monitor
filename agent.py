import os
import json
import requests
import resend
from groq import Groq

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
        resend.Emails.send({
            "from": "SkollagAgent <onboarding@resend.dev>",
            "to": RECIPIENT_EMAIL,
            "subject": subject,
            "html": f"<h2>Ny ändring i Skollagen registrerad</h2><p>{html_content}</p>"
        })
        print(f"E-post skickades till {RECIPIENT_EMAIL}!")
    except Exception as e:
        print(f"E-POSTFEL: {e}")

def run_monitor():
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        print("FEL: GROQ_API_KEY saknas i secrets!")
        return

    client = Groq(api_key=groq_key)
    
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
        3. Håll språket professionellt, tydligt och lättillgängligt på svenska.
        """

        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "Du är en juridisk expert på svensk skolrätt och pedagogisk lagstiftning."
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="llama-3.3-70b-versatile",
            )
            analysis_text = chat_completion.choices[0].message.content
        except Exception as e:
            print(f"AI-FEL: {e}")
            analysis_text = f"Ny ändring registrerad i Skollagen: {latest_change['titel']}."

        subject = f"Lagändring Skollagen: {latest_change['titel']}"
        body = f"{analysis_text}\n\nLäs mer i sin helhet här: {latest_change['url']}"
        
        send_email_notification(subject, body)
        save_last_seen_id(latest_change["id"])
    else:
        print("Inga nya ändringar i Skollagen sedan förra kontrollen.")

if __name__ == "__main__":
    run_monitor()
