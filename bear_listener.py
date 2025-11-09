import os
import sys
import json
import queue
import time
import requests
import sounddevice as sd
from vosk import Model, KaldiRecognizer

# ----- CONFIG -----
# your local FastAPI brain
BRAIN_URL = os.getenv("BEAR_BRAIN_URL", "http://127.0.0.1:8001/chat")
DEVICE_API_KEY = os.getenv("DEVICE_API_KEY", "test123")

# azure speech (tts)
import azure.cognitiveservices.speech as speechsdk

AZURE_SPEECH_KEY = os.getenv(
    "AZURE_SPEECH_KEY",
    "Ac0TlExZi97qWi2NAHNLra5oA2UUAcqkQ8LFc1TklGyR0gObvu8IJQQJ99BKACHYHv6XJ3w3AAAYACOGKS1t",
)
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus2")
AZURE_VOICE = os.getenv("AZURE_VOICE", "en-US-AnaNeural")

WAKEWORDS = ["bear", "hello bear", "hey bear"]
WAKE_COOLDOWN_SEC = 4.0
last_wake_time = 0.0

MODEL_PATH = "vosk_model"
SAMPLE_RATE = 16000
# -------------------


def make_speech_synthesizer():
    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION
    )
    speech_config.speech_synthesis_voice_name = AZURE_VOICE
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
    return speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config
    )


def speak(text: str):
    try:
        synth = make_speech_synthesizer()
        synth.speak_text_async(text).get()
    except Exception as e:
        print(f"TTS error: {e}")


def call_bear_brain(user_text: str) -> str:
    payload = {
        "message": user_text,
        "conversation_id": "home",  # just something stable for your device
    }
    headers = {
        "Content-Type": "application/json",
        "X-Bear-Key": DEVICE_API_KEY,
    }
    try:
        resp = requests.post(
            BRAIN_URL, headers=headers, data=json.dumps(payload), timeout=8
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("reply", "The bear didn't say anything.")
        else:
            print(f"brain HTTP {resp.status_code}: {resp.text}")
            return "I couldn't reach the bear brain right now."
    except Exception as e:
        print(f"brain error: {e}")
        return "I couldn't reach the bear brain right now."


def looks_like_wakeword(text: str) -> bool:
    t = text.lower().strip()
    if not t:
        return False

    # exact matches
    for w in WAKEWORDS:
        if t == w:
            return True

    # short phrases that include the word bear
    if "bear" in t and len(t.split()) <= 4:
        return True

    return False


def listen_for_one_utterance(model):
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    rec.SetWords(True)

    q2 = queue.Queue()

    def cb(indata, frames, time_, status):
        if status:
            print(status, file=sys.stderr)
        q2.put(bytes(indata))

    print("Listening for user sentence...")
    collected_text = ""
    start_time = time.time()

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=cb,
    ):
        while True:
            if time.time() - start_time > 7:  # listen up to 7 seconds
                break
            try:
                data = q2.get(timeout=0.5)
            except queue.Empty:
                continue

            if rec.AcceptWaveform(data):
                j = json.loads(rec.Result())
                collected_text = j.get("text", "").strip()
                break

    return collected_text


def main():
    global last_wake_time

    if not os.path.isdir(MODEL_PATH):
        print(f"Vosk model not found at {MODEL_PATH}")
        sys.exit(1)

    print(f"Using Azure Speech in region: {AZURE_SPEECH_REGION}")
    print("Wakeword: listening for 'bear' ...")

    model = Model(MODEL_PATH)
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    recognizer.SetWords(True)

    q = queue.Queue()

    def audio_callback(indata, frames, time_, status):
        if status:
            print(status, file=sys.stderr)
        q.put(bytes(indata))

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=audio_callback,
    ):
        while True:
            data = q.get()
            if recognizer.AcceptWaveform(data):
                result = recognizer.Result()
                j = json.loads(result)
                text = j.get("text", "").strip()
                if not text:
                    continue

                if looks_like_wakeword(text):
                    now = time.time()
                    if now - last_wake_time < WAKE_COOLDOWN_SEC:
                        continue
                    last_wake_time = now

                    print(f"Wakeword detected: {text}")
                    speak("I'm listening...")
                    print("BearBuddy: I'm listening...")

                    user_text = listen_for_one_utterance(model)
                    if user_text:
                        print(f"Heard: {user_text}")
                        reply = call_bear_brain(user_text)
                        print(f"Bear: {reply}")
                        speak(reply)
                    else:
                        print("Heard nothing.")


if __name__ == "__main__":
    main()
