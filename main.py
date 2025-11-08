cat > main.py <<'EOF'
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import requests
import os
import json
import subprocess
from pathlib import Path
import time
from datetime import datetime
import glob

from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# -------------------------------------------------
# AZURE OPENAI (chat) CONFIG
# -------------------------------------------------

import os

AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
API_VERSION = os.getenv("API_VERSION")

if not AZURE_OPENAI_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT:
    # you can log or even raise here
    print("⚠️ Azure OpenAI env vars are missing")

if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
    print("⚠️ Azure Speech env vars are missing")


# -------------------------------------------------

SETTINGS_FILE = "settings.json"
CURRICULUM_FILE = "curriculum.json"          # latest one
CURRICULUM_STORE_FILE = "curriculum_store.json"  # aggregated
PROJECT_DIR = Path(__file__).parent


# ------------- helpers for settings/curriculum -------------
def load_settings() -> dict:
    defaults = {
        "child_name": "Buddy",
        "age_level": 4,
        "focus_topics": ["colors", "shapes"],
        "voice_style": "toddler",
        "use_curriculum": True,
        "wifi_configured": False,
    }

    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            file_data = json.load(f)
        defaults.update(file_data)

    # make sure both new keys exist
    if "use_curriculum" not in defaults:
        defaults["use_curriculum"] = True
    if "wifi_configured" not in defaults:
        defaults["wifi_configured"] = False

    # write back so the file on disk is updated
    save_settings(defaults)
    return defaults


def save_settings(data: dict):
    if "use_curriculum" not in data:
        data["use_curriculum"] = True
    if "wifi_configured" not in data:
        data["wifi_configured"] = False
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_curriculum() -> dict:
    if os.path.exists(CURRICULUM_FILE):
        with open(CURRICULUM_FILE, "r") as f:
            return json.load(f)
    return {}


def save_curriculum(data: dict):
    with open(CURRICULUM_FILE, "w") as f:
        json.dump(data, f, indent=2)


def append_curriculum_store(entry: dict):
    # keep a big list of all plans
    store = []
    if os.path.exists(CURRICULUM_STORE_FILE):
        with open(CURRICULUM_STORE_FILE, "r") as f:
            try:
                store = json.load(f)
            except Exception:
                store = []
    store.append(entry)
    with open(CURRICULUM_STORE_FILE, "w") as f:
        json.dump(store, f, indent=2)


def load_curriculum_aggregate() -> list[dict]:
    if os.path.exists(CURRICULUM_STORE_FILE):
        with open(CURRICULUM_STORE_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []
# ------------------------------------------------------------
def extract_topic(user_text: str) -> str:
    """
    Super simple topic grabber.
    We take the main noun-y bit from what the child said.
    """
    if not user_text:
        return ""
    text = user_text.lower()

    # if user says "my favorite is X" or "i like X"
    for starter in ["my favorite is", "my favourite is", "i like", "i love", "let's talk about", "tell me about"]:
        if starter in text:
            return text.split(starter, 1)[1].strip()

    # fallback: just return the whole thing, model will see it
    return user_text.strip()

def build_system_prompt(profile: dict, curriculum_data=None):
    name = profile.get("child_name", "buddy")
    age = profile.get("age_level", 4)
    focus = profile.get("focus_topics", [])
    current_topic = profile.get("current_topic", "").strip()

    base = [
        "You are BearBuddy, a warm, gentle, playful talking bear for a preschooler.",
        "Your first rule: keep the conversation on the child's current topic.",
        "Answer the child directly before offering anything extra.",
        "Keep replies short (1–3 sentences), kind, and playful.",
        f"The child's name is {name}. The child is about {age} years old.",
    ]

    if current_topic:
        base.append(
            f"The child is currently talking about: {current_topic}. Stay on this topic unless the child clearly changes it."
        )
        base.append(
            "Do not reinterpret similar-sounding words to something else. Assume the child meant the topic they said."
        )
    else:
        base.append("If the child has no clear topic, you may suggest something fun.")

    if focus:
        base.append(
            f"If the child seems unsure, you can gently use these interests: {', '.join(focus)}."
        )

    # curriculum = low priority
    if curriculum_data:
        base.append(
            "The parent uploaded preschool lesson plans. These are optional and should not override the child's current topic."
        )
        base.append(
            "Use a plan only when the child asks for an activity or has no topic."
        )
        last_items = curriculum_data[-3:]
        for item in last_items:
            theme = item.get("theme", "")
            acts = item.get("activities", [])
            base.append(f"(optional plan) theme: {theme}; activities: {acts}")

    return "\n".join(base)




# ---------------- OCR helpers ----------------
def ocr_image_to_text(file_bytes: bytes) -> str | None:
    url = f"{AZURE_VISION_ENDPOINT}/vision/v3.2/read/analyze"
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_VISION_KEY,
        "Content-Type": "application/octet-stream"
    }
    try:
        resp = requests.post(url, headers=headers, data=file_bytes)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("OCR start failed:", e)
        return None

    operation_url = resp.headers.get("Operation-Location")
    if not operation_url:
        return None

    # poll
    while True:
        r = requests.get(
            operation_url,
            headers={"Ocp-Apim-Subscription-Key": AZURE_VISION_KEY}
        )
        data = r.json()
        status = data.get("status")
        if status in ("succeeded", "failed"):
            break
        time.sleep(0.5)

    if status != "succeeded":
        return None

    lines = []
    for read_result in data["analyzeResult"]["readResults"]:
        for line in read_result["lines"]:
            lines.append(line["text"])
    return "\n".join(lines)


# -------- LLM-based plan extractor (generic) -------
def extract_plan_with_llm(raw_text: str) -> dict:
    """
    We ask Azure to normalize whatever we OCR'd.
    """
    url = (
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/"
        f"{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version={API_VERSION}"
    )

    system_msg = (
        "You are a preschool curriculum normalizer. "
        "You will be given noisy OCR text from a weekly plan. "
        "Return a compact JSON with keys: theme (string), "
        "activities (array of short strings), letters (array), "
        "numbers (array), focus_skills (array), raw_summary (string). "
        "Keep activities kid-safe. If something isn't present, return an empty array."
    )
    user_msg = f"OCR TEXT:\n{raw_text}\n----\nReturn ONLY JSON."

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_KEY,
    }
    payload = {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.2,
    }

    resp = requests.post(url, headers=headers, json=payload)
    try:
        data = resp.json()
    except Exception:
        return {
            "theme": None,
            "activities": [],
            "letters": [],
            "numbers": [],
            "focus_skills": [],
            "raw_summary": raw_text[:500]
        }

    if "choices" not in data:
        return {
            "theme": None,
            "activities": [],
            "letters": [],
            "numbers": [],
            "focus_skills": [],
            "raw_summary": raw_text[:500]
        }

    content = data["choices"][0]["message"]["content"]
    # try to parse JSON
    try:
        parsed = json.loads(content)
        return parsed
    except Exception:
        return {
            "theme": None,
            "activities": [],
            "letters": [],
            "numbers": [],
            "focus_skills": [],
            "raw_summary": raw_text[:500]
        }


def make_curriculum_filename() -> str:
    date_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"curriculum_{date_str}.json"
# ------------------------------------------------


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


# ---- single OR multiple upload in one endpoint ----
@app.post("/upload-plans")
async def upload_plans(files: list[UploadFile] = File(...)):
    results = []
    for file in files:
        file_bytes = await file.read()
        text = ocr_image_to_text(file_bytes)
        if not text:
            results.append({
                "file": file.filename,
                "status": "error",
                "reason": "OCR failed – check endpoint/key or try fewer files."
            })
            continue

        extracted = extract_plan_with_llm(text)
        fname = make_curriculum_filename()
        with open(fname, "w") as f:
            json.dump(extracted, f, indent=2)

        # update “current” plan
        save_curriculum(extracted)
        append_curriculum_store(extracted)

        results.append({
            "file": file.filename,
            "status": "ok",
            "saved_as": fname,
            "theme": extracted.get("theme"),
            "activities_count": len(extracted.get("activities") or []),
        })

        # be nice to vision
        time.sleep(1)

    return {"status": "ok", "results": results}
# ---------------------------------------------------

def generate_bear_reply(user_msg: str, request: Request) -> str:
    # 1) auth
    api_key_header = request.headers.get("X-Bear-Key")
    expected = os.getenv("DEVICE_API_KEY")
    if expected and api_key_header != expected:
        return "I don't know this bear yet. Ask a grownup to connect me."

    # 2) load settings
    settings = load_settings()

    # 3) onboarding gate
    if not settings.get("wifi_configured", False):
        return "I still need to finish setup. Please finish connecting me first."

    # 4) message
    user_msg = (user_msg or "").strip()
    if not user_msg:
        return "Can you say that again, honeybear?"

    # 5) profile
    profile = settings

    # --- NEW: update current_topic ---
    current_topic = extract_topic(user_msg)
    if current_topic:
        settings["current_topic"] = current_topic
        save_settings(settings)
    # -------------------------------

    # 6) curriculum
    curriculum_data = None
    if settings.get("use_curriculum", True):
        curriculum_data = load_curriculum_aggregate()

    # 7) system prompt
    system_prompt = build_system_prompt(profile, curriculum_data)

    # 8) call Azure OpenAI
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "messages": messages,
        "max_tokens": 250,
        "temperature": 0.7,
        "top_p": 0.95,
    }
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_KEY,
    }
    url = (
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/"
        f"{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version={API_VERSION}"
    )

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        data = resp.json()
    except Exception as e:
        return f"Error calling Azure: {e}"

    if "choices" not in data:
        return f"Error from Azure: {data}"

    answer = data["choices"][0]["message"]["content"]
    # strip emojis for TTS
    answer = answer.encode("ascii", errors="ignore").decode()
    return answer


@app.post("/chat")
def chat(body: dict, request: Request):
    api_key_header = request.headers.get("X-Bear-Key")
    expected = os.getenv("DEVICE_API_KEY")
    if expected and api_key_header != expected:
        return {"reply": "I don't know this bear yet. Ask a grownup to connect me."}

    user_msg = body.get("message") or ""
    answer = generate_bear_reply(user_msg, request)
    return {"reply": answer}

@app.post("/chat-audio")
def chat_audio(body: dict, request: Request):
    # 1) re-use the same auth as /chat
    api_key_header = request.headers.get("X-Bear-Key")
    expected = os.getenv("DEVICE_API_KEY")
    if expected and api_key_header != expected:
        return {"reply": "I don't know this bear yet. Ask a grownup to connect me."}

    # 2) load settings and make sure device is set up
    settings = load_settings()
    if not settings.get("wifi_configured", False):
        return {"reply": "I still need to finish setup. Please finish connecting me first."}

    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        return {"reply": "Can you say that again, honeybear?"}

    # 3) build prompt exactly like /chat does
    profile = settings
    curriculum_data = None
    if settings.get("use_curriculum", True):
        curriculum_data = load_curriculum_aggregate()

    system_prompt = build_system_prompt(profile, curriculum_data)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "messages": messages,
        "max_tokens": 250,
        "temperature": 0.7,
        "top_p": 0.95,
    }
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_KEY,
    }
    url = (
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/"
        f"{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version={API_VERSION}"
    )

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        data = resp.json()
    except Exception as e:
        return {"reply": f"Error calling Azure: {e}"}

    if "choices" not in data:
        return {"reply": f"Error from Azure: {data}"}

    reply = data["choices"][0]["message"]["content"]
    reply = reply.encode("ascii", errors="ignore").decode()

    # 4) now TTS in the cloud
    if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
        # speech not configured in Azure App Settings
        return {"reply": reply, "note": "Speech not configured on server"}

    tts_url = f"https://{AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
    ssml = f"""
    <speak version='1.0' xml:lang='en-US'>
      <voice name='en-US-AnaNeural'>{reply}</voice>
    </speak>
    """.strip()

    tts_headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
    }

    tts_resp = requests.post(tts_url, headers=tts_headers, data=ssml.encode("utf-8"))
    if tts_resp.status_code != 200:
        # fall back to text if voice fails
        return {"reply": reply, "note": f"TTS failed: {tts_resp.status_code}"}

    return StreamingResponse(
        iter([tts_resp.content]),
        media_type="audio/mpeg",
        headers={"X-Bear-Reply": reply},
    )

# ---------- simple HTML GUI ----------
@app.get("/ui", response_class=HTMLResponse)
def settings_ui():
    return """
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>BearBuddy Settings</title>
      <style>
        body { font-family: Arial, sans-serif; max-width: 520px; margin: 20px auto; }
        label { display:block; margin-top: 12px; }
        input[type=text], input[type=number] { width: 100%; padding: 6px; }
        button { margin-top: 16px; padding: 8px 14px; }
        .small { font-size: 0.8rem; color: #666; }
        hr { margin: 20px 0; }
      </style>
    </head>
    <body>
      <h2>BearBuddy Settings</h2>
      <label>Child name
        <input id="child_name" />
      </label>

      <label>Age level
        <input id="age_level" type="number" min="2" max="10" />
      </label>

      <label>Focus topics (comma separated)
        <input id="focus_topics" placeholder="colors, shapes" />
      </label>

      <label>Voice style
        <input id="voice_style" placeholder="toddler" />
      </label>

      <label style="margin-top:14px;">
        <input id="use_curriculum" type="checkbox" unchecked />
        Let BearBuddy use uploaded preschool plans
      </label>

    <label style="margin-top:14px;">
        <input id="wifi_configured" type="checkbox" />
        Device is set up / connected
        </label>

      <button onclick="saveSettings()">Save</button>
      <p id="status" class="small"></p>



      <hr>
      <h3>Upload plan(s)</h3>
      <input type="file" id="planfiles" accept="image/*,.pdf" multiple />
      <button onclick="uploadPlans()">Upload</button>
      <p class="small">You can upload one or several. If Azure rate-limits, try fewer.</p>
      <p id="planstatus" class="small"></p>

      <script>
        async function loadSettings() {
          const res = await fetch('/settings');
          const data = await res.json();
          document.getElementById('child_name').value = data.child_name || '';
          document.getElementById('age_level').value = data.age_level || 4;
          document.getElementById('focus_topics').value = (data.focus_topics || []).join(', ');
          document.getElementById('voice_style').value = data.voice_style || 'toddler';
          document.getElementById('use_curriculum').checked = (data.use_curriculum !== false);
         document.getElementById('wifi_configured').checked = (data.wifi_configured === true);   // <-- NEW
  }

        async function saveSettings() {
          const body = {
            child_name: document.getElementById('child_name').value,
            age_level: Number(document.getElementById('age_level').value),
            focus_topics: document.getElementById('focus_topics').value
              .split(',').map(s => s.trim()).filter(s => s.length > 0),
            voice_style: document.getElementById('voice_style').value,
            use_curriculum: document.getElementById('use_curriculum').checked,
            wifi_configured: document.getElementById('wifi_configured').checked,
          };
          const res = await fetch('/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
          });
          document.getElementById('status').innerText = res.ok ? 'Saved ✔' : 'Error saving ❌';
        }

        async function uploadPlans() {
          const input = document.getElementById('planfiles');
          if (!input.files.length) {
            document.getElementById('planstatus').innerText = 'Choose files first.';
            return;
          }
          const formData = new FormData();
          for (let i = 0; i < input.files.length; i++) {
            formData.append('files', input.files[i]);
          }
          const res = await fetch('/upload-plans', {
            method: 'POST',
            body: formData
          });
          const data = await res.json();
          if (data.status === 'ok') {
            const msgs = data.results.map(r => {
              if (r.status === 'ok') {
                return r.file + ': ' + (r.theme || 'no theme') + ' (' + r.activities_count + ' activities)';
              } else {
                return r.file + ': ' + (r.reason || 'error');
              }
            }).join(' | ');
            document.getElementById('planstatus').innerText = msgs;
          } else {
            document.getElementById('planstatus').innerText = 'Upload failed ❌';
          }
        }

        loadSettings();
      </script>
    </body>
    </html>
    """
# ------------------------------------


@app.post("/update")
def update_code():
    repo_path = os.path.abspath(".")
    try:
        out = subprocess.check_output(
            ["git", "-C", repo_path, "pull"],
            stderr=subprocess.STDOUT
        )
        return {"status": "ok", "output": out.decode()}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "output": e.output.decode()}
    except Exception as e:
        return {"status": "error", "output": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
EOF
