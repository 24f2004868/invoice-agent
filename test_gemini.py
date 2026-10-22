
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY not found. Check your .env file."
    )

client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents="Reply with exactly: Gemini connection successful"
    )
    print(response.text)
except Exception as error:
    print("Error type:", type(error).__name__)
    print("Error details:", str(error)[:1000])
