"""Ek baar chalao. Browser khulega, channel wale Gmail se login karo.
Is se token.json ban jayegi, phir main.py upload kar sakega.

    pip install google-auth-oauthlib
    python get_token.py client_secret.json
"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

with open("token.json", "w") as f:
    f.write(creds.to_json())
print("\ntoken.json ban gayi. Ab 'python main.py --dry' se test karo.")
