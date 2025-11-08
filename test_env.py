import os
from dotenv import load_dotenv

load_dotenv()

print("AZURE_OPENAI_KEY =", os.getenv("AZURE_OPENAI_KEY"))
print("AZURE_OPENAI_ENDPOINT =", os.getenv("AZURE_OPENAI_ENDPOINT"))
print("AZURE_OPENAI_DEPLOYMENT =", os.getenv("AZURE_OPENAI_DEPLOYMENT"))
