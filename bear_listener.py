import json
import time
import requests
import os

from dotenv import load_dotenv   # NEW

# ---- Vosk + mic ----
from vosk import Model, KaldiRecognizer
import pyaudio

# ---- Azure Speech (for real command + TTS) ----
import azure.cognitiveservices.speech as speechsdk

# ---------------- CONFIG ----------------
VOSK_MODEL_PATH = r"C:\mini_ERP\vosk_model"  # change to your model path
BEAR_API = "https://web-app-8367-bqbuhkdmb2fedwau.centralus-01.azurewebsites.net/chat"


# load .env so AZURE_* and DEVICE_API_KEY work
load_dotenv()

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
DEVICE_API_KEY = os.getenv("DEVICE_API_KEY", "test123")  # <- same as backend
# ----------------------------------------


def init_azure_speech():
    if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
        raise ValueError("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION in .env")
    print(f"Using Azure Speech in region: {AZURE_SPEECH_REGION}")
    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_SPEECH_KEY,
        region=AZURE_SPEECH_REGION
    )
    speech_config.speech_synthesis_voice_name = "en-US-AnaNeural"
    return speech_config


def tts(speech_config, text: str):
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
    synthesizer.speak_text_async(text).get()


def call_bear(text: str) -> str:
    try:
        headers = {"X-Bear-Key": DEVICE_API_KEY}  # <-- IMPORTANT
        r = requests.post(
            BEAR_API,
            json={"message": text},
            headers=headers,
            timeout=8
        )
        data = r.json()
        return data.get("reply", "I didn't quite get that.")
    except Exception as e:
        return f"I can't reach the bear brain right now. ({e})"


def capture_with_azure(speech_config, timeout_sec=7):
    """After wakeword, listen with Azure for the actual sentence."""
    audio_config = speechsdk.AudioConfig(use_default_microphone=True)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config
    )

    chunks = []

    def on_recognized(evt):
        if evt.result.text:
            chunks.append(evt.result.text)

    recognizer.recognized.connect(on_recognized)
    recognizer.start_continuous_recognition()
    print("BearBuddy: I'm listening...")

    start = time.time()
    while time.time() - start < timeout_sec:
        time.sleep(0.2)

    recognizer.stop_continuous_recognition()
    final_text = " ".join(chunks).strip()
    print("Heard:", final_text)
    return final_text


def listen_for_wakeword(model_path: str):
    """Block here until we hear 'bear', 'buddy bear', or 'kiera bear'."""
    print("Wakeword: listening for 'bear' ...")

    model = Model(model_path)

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16,
                     channels=1,
                     rate=16000,
                     input=True,
                     frames_per_buffer=8000)
    stream.start_stream()

    recognizer = KaldiRecognizer(model, 16000)

    while True:
        data = stream.read(4000, exception_on_overflow=False)
        if len(data) == 0:
            continue

        if recognizer.AcceptWaveform(data):
            result = recognizer.Result()
            j = json.loads(result)
            text = j.get("text", "").lower()
            if text:
                if ("bear" in text) or ("buddy bear" in text) or ("kiera bear" in text):
                    print("Wakeword detected:", text)
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
                    return
        else:
            pass


def capture_followup_with_azure(speech_config, timeout_sec=6):
    """Short 'I'm still here' window after TTS."""
    audio_config = speechsdk.AudioConfig(use_default_microphone=True)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config
    )

    parts = []

    def on_recognized(evt):
        if evt.result.text:
            parts.append(evt.result.text)

    recognizer.recognized.connect(on_recognized)
    recognizer.start_continuous_recognition()
    print("🐻 (still listening for a moment...)")

    start = time.time()
    while time.time() - start < timeout_sec:
        time.sleep(0.2)

    recognizer.stop_continuous_recognition()
    return " ".join(parts).strip()


def main():
    speech_config = init_azure_speech()

    while True:
        # 1. wait for wakeword
        listen_for_wakeword(VOSK_MODEL_PATH)

        # 2. first user message (the main one)
        user_text = capture_with_azure(speech_config, timeout_sec=7)
        if not user_text:
            continue

        reply = call_bear(user_text)
        print("Bear:", reply)
        tts(speech_config, reply)

        # 3. follow-up loop: keep listening until we get silence
        while True:
            follow = capture_followup_with_azure(speech_config, timeout_sec=6)
            if not follow:
                break
            reply2 = call_bear(follow)
            print("Bear:", reply2)
            tts(speech_config, reply2)


if __name__ == "__main__":
    main()
