import json
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

@tool
def fetch_contact(name: str) -> str:
    """Lookup an email address for a given name from the contacts database."""
    try:
        print(f"Fetching contact for name: {name}")
        with open("contacts.json", "r") as f:
            contacts = json.load(f)
        
        # Case-insensitive search
        for contact_name, email in contacts.items():
            if contact_name.lower() in name.lower():
                print(f"Found contact: {contact_name} -> {email}")
                return email
        print(f"Contact {name} not found in contacts.json")
        return f"Contact {name} not found."
    except Exception as e:
        print(f"Error reading contacts.json: {str(e)}")
        return f"Error reading contacts: {str(e)}"

@tool
def send_email(recipient_email: str, subject: str, body: str) -> str:
    """
    Sends an email to the recipient. 
    Call this ONLY after the user has explicitly confirmed the draft.
    """
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    if not sender_email or not sender_password:
        print("Email credentials are not set in the environment.")
        return "Error: Email credentials are not set in the environment."

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Standard Gmail SMTP configuration
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {recipient_email} with subject '{subject}'")
        return f"Email successfully sent to {recipient_email}!"
    except Exception as e:
        print(f"Failed to send email to {recipient_email}. Error: {str(e)}")
        return f"Failed to send email. Error: {str(e)}"