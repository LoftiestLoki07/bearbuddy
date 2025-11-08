import azure.cognitiveservices.speech as speechsdk
import requests

# 1) Azure Speech
SPEECH_KEY = "Ac0TlExZi97qWi2NAHNLra5oA2UUAcqkQ8LFc1TklGyR0gObvu8IJQQJ99BKACHYHv6XJ3w3AAAYACOGKS1t"
SPEECH_REGION = "eastus2"

# 2) Your FastAPI backend
BEAR_API = "http://localhost:8001/chat"
SETTINGS_API = "http://localhost:8001/settings"

# 3) toggle: use server-side settings or local
USE_SERVER_SETTINGS = True

# 4) local fallback profile
PROFILE = {
    "child_name": "Kiera",
    "age_level": 4,
    "focus_topics": ["colors", "shapes"]
}


def stt() -> str:
    speech_config = speechsdk.SpeechConfig(
        subscription=SPEECH_KEY,
        region=SPEECH_REGION
    )
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config)
    print("Say something to BearBuddy...")
    result = recognizer.recognize_once()
    return result.text or ""


def tts(text: str) -> None:
    speech_config = speechsdk.SpeechConfig(
        subscription=SPEECH_KEY,
        region=SPEECH_REGION
    )
    voice = "en-US-AnaNeural"
    speech_config.speech_synthesis_voice_name = voice
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

    ssml = f"""
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
           xmlns:mstts="https://www.w3.org/2001/mstts"
           xml:lang="en-US">
      <voice name="{voice}">
        <prosody pitch="+6%" rate="-5%">
          {text}
        </prosody>
      </voice>
    </speak>
    """
    synthesizer.speak_ssml_async(ssml).get()


def get_server_settings() -> dict:
    try:
        resp = requests.get(SETTINGS_API, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print("WARNING: /settings returned", resp.status_code, resp.text)
    except Exception as e:
        print("WARNING: could not reach settings API:", e)
    return {}


def main():
    # choose profile
    if USE_SERVER_SETTINGS:
        server_profile = get_server_settings()
        if server_profile:
            print("Using server profile:", server_profile)
        else:
            print("Falling back to local profile.")
            server_profile = PROFILE
    else:
        server_profile = PROFILE

    # listen
    user_text = stt()
    print("You said:", user_text)

    # talk to bear
    try:
        if USE_SERVER_SETTINGS:
            payload = {"message": user_text}  # let backend add settings
        else:
            payload = {"profile": server_profile, "message": user_text}

        resp = requests.post(BEAR_API, json=payload, timeout=10)
        print("DEBUG status:", resp.status_code)
        print("DEBUG body:", resp.text)
        data = resp.json()
        reply = data.get("reply", "I couldn't answer right now.")
    except Exception as e:
        print("Error calling bear backend:", e)
        reply = "Sorry, I couldn't talk right now."

    print("BearBuddy:", reply)
    tts(reply)


if __name__ == "__main__":
    main()
