import azure.cognitiveservices.speech as speechsdk
import requests

# 1) FILL THESE IN FROM AZURE
SPEECH_KEY = "Ac0TlExZi97qWi2NAHNLra5oA2UUAcqkQ8LFc1TklGyR0gObvu8IJQQJ99BKACHYHv6XJ3w3AAAYACOGKS1t"
SPEECH_REGION = "eastus2"  # e.g. "eastus"

# 2) THIS IS YOUR PHASE 2 API
BEAR_API = "http://localhost:8001/chat"

# 3) PROFILE YOU SEND TO THE BEAR
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
    # you can still pick a neural voice, then tweak it
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



def main():
    text = stt()
    print("You said:", text)

    resp = requests.post(
        BEAR_API,
        json={"profile": PROFILE, "message": text}
    )

    print("DEBUG status:", resp.status_code)
    print("DEBUG body:", resp.text)

    data = resp.json()
    reply = data["reply"]

    print("BearBuddy:", reply)
    tts(reply)


if __name__ == "__main__":
    main()