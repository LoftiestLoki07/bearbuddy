from fastapi import FastAPI
import requests
import os
import json
import subprocess

app = FastAPI()

# -------------------------------------------------
# AZURE CONFIG
# -------------------------------------------------
# your Azure OpenAI endpoint (no trailing slash)
AZURE_ENDPOINT = "https://eelke-mhp17cak-japaneast.openai.azure.com"
# your key (better: store in env and read with os.getenv)
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY", "1quI8prilhX7u5ijPVOtfRyzS5CDzEwOD6ig53lAVFOCZsSE52JoJQQJ99BKACi0881XJ3w3AAAAACOGrjWs")
# the deployment name you created in Azure OpenAI
AZURE_DEPLOYMENT = "gpt-4o"
# API version your workspace supports
API_VERSION = "2024-10-21"
# -------------------------------------------------

# where we’ll store the current teddy settings on disk
SETTINGS_FILE = "settings.json"

# path to your project (change on Pi to /home/pi/bearbuddy)
PROJECT_DIR = Path(__file__).parent  # C:\mini_ERP now


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "child_name": "Buddy",
        "age_level": 4,
        "focus_topics": ["colors", "shapes"],
        "voice_style": "toddler"
    }


def save_settings(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)


def build_system_prompt(profile: dict) -> str:
    age = profile.get("age_level", 5)
    focus = ", ".join(profile.get("focus_topics", [])) or "general kid topics"
    name = profile.get("child_name", "friend")
    return (
        f"You are BearBuddy, a talking teddy for young children.\n"
        f"Child name: {name}\n"
        f"Child age: {age}\n"
        f"Focus today: {focus}\n"
        "Speak in short, simple sentences. Be warm and playful. "
        "Avoid scary or adult topics."
    )


@app.get("/")
def health():
    return {"status": "ok", "service": "bearbuddy"}


@app.get("/settings")
def get_settings():
    return load_settings()


@app.post("/settings")
def post_settings(body: dict):
    save_settings(body)
    return {"status": "ok"}


@app.post("/chat")
def chat(body: dict):
    if "profile" in body:
        profile = body["profile"]
    else:
        profile = load_settings()

    user_msg = body.get("message", "")

    system_prompt = build_system_prompt(profile)

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_API_KEY,
    }

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
    }

    url = (
        f"{AZURE_ENDPOINT}/openai/deployments/"
        f"{AZURE_DEPLOYMENT}/chat/completions?api-version={API_VERSION}"
    )

    resp = requests.post(url, headers=headers, json=payload)
    data = resp.json()

    if "choices" not in data:
        return {"reply": f"Error from Azure: {data}"}

    answer = data["choices"][0]["message"]["content"]
    return {"reply": answer}


# --------- UPDATE ENDPOINT ----------
@app.post("/update")
def update_code():
    """
    Pull latest code from git and (optionally) restart service.
    Works best on the Pi.
    """
    try:
        # run 'git pull' in the project dir
        result = subprocess.check_output(
            ["git", "-C", str(PROJECT_DIR), "pull"],
            stderr=subprocess.STDOUT
        )
        output = result.decode()

        # OPTIONAL: on Pi, uncomment to restart your service
        # subprocess.run(["sudo", "systemctl", "restart", "bearbuddy"])

        return {"status": "ok", "output": output}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "output": e.output.decode() if e.output else str(e)
        }
    except Exception as e:
        return {"status": "error", "output": str(e)}
# ------------------------------------