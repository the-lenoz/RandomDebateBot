# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_CREDENTIALS_PATH = os.getenv("GOOGLE_API_CREDENTIALS_PATH", "credentials.json") # Default if not set

if not BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN is not set. Please set it in .env or as an environment variable.")
    exit(1)

# For the mock Google Meet, GOOGLE_API_CREDENTIALS_PATH is used but the file doesn't need to be valid.
# For a real implementation, ensure this path points to your actual Google Cloud service account JSON key.
if GOOGLE_API_CREDENTIALS_PATH == "credentials.json":
    print(f"Warning: GOOGLE_API_CREDENTIALS_PATH is using the default '{GOOGLE_API_CREDENTIALS_PATH}'. "
          f"Ensure this file exists or set the path correctly for real Google Meet integration.")

# Example of admin IDs, not used in this version but good for future extensions
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(admin_id) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip().isdigit()]