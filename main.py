import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# we’ll try Azure OpenAI first
from openai import AzureOpenAI
from fastapi.middleware.cors import CORSMiddleware

# 👇 add this
from dotenv import load_dotenv
load_dotenv()  # this will read .env sitting next to main.py

app = FastAPI()

DEVICE_API_KEY = os.getenv("DEVICE_API_KEY", "test123")

# Azure OpenAI config (set these in .env or system env)
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")  # e.g. https://my-ai.openai.azure.com
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")  # your chat model deployment name

client = None
if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY and AZURE_OPENAI_DEPLOYMENT:
    client = AzureOpenAI(
        api_key=AZURE_OPENAI_KEY,
        api_version="2024-08-01-preview",
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
    )


class ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None


def call_azure_openai(user_msg: str) -> str | None:
    if client is None:
        print("Azure client NOT initialized – check AZURE_OPENAI_* env vars")
        return None

    try:
        resp = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are BearBuddy, a warm, short, friendly assistant for a household. "
                        "You talk like you would to a kid: clear, kind, 1–2 sentences max."
                    ),
                },
                {"role": "user", "content": user_msg},
            ],
            max_tokens=120,
            temperature=0.7,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"Azure OpenAI error: {e}")
        return None



@app.post("/chat")
async def chat(body: ChatBody, request: Request):
    # check device key
    key = request.headers.get("X-Bear-Key")
    if DEVICE_API_KEY and key != DEVICE_API_KEY:
        return JSONResponse(
            status_code=401,
            content={
                "reply": "I don't know this bear yet. Ask a grownup to connect me."
            },
        )

    user_msg = (body.message or "").strip()
    if not user_msg:
        return {"reply": "I didn't hear anything."}

    # 1) try Azure OpenAI
    ai_reply = call_azure_openai(user_msg)
    if ai_reply:
        return {"reply": ai_reply}

    # 2) fallback if Azure not configured / failed
    return {"reply": f"You said: {user_msg}"}


@app.get("/")
def root():
    return {"status": "ok"}
