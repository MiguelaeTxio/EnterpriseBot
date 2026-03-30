# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/trigger_outbound_call.py
import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

def trigger_validation_call():
    project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
    load_dotenv(os.path.join(project_root, ".env"))

    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    api_key_sid = os.getenv('TWILIO_API_KEY_SID')
    api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
    from_number = os.getenv('TWILIO_PHONE_NUMBER')
    to_number = "+34688360595"
    
    webhook_url = "https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/inbound/"

    try:
        client = Client(api_key_sid, api_key_secret, account_sid)
        print(f"# [AUDIT] Disparando llamada a {to_number}...")
        call = client.calls.create(
            url=webhook_url,
            to=to_number,
            from_=from_number,
            method='POST'
        )
        print(f"# [SUCCESS] CallSid: {call.sid}")
    except Exception as e:
        print(f"# [ERROR] {str(e)}")

if __name__ == "__main__":
    trigger_validation_call()
