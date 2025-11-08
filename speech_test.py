import azure.cognitiveservices.speech as speechsdk

speech_key = "Ac0TlExZi97qWi2NAHNLra5oA2UUAcqkQ8LFc1TklGyR0gObvu8IJQQJ99BKACHYHv6XJ3w3AAAYACOGKS1t"
service_region = "eastus2"  # e.g. "eastus"

# 1) speech to text
speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config)

print("Say something...")
result = speech_recognizer.recognize_once()
print("You said:", result.text)

# 2) text to speech
speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"
speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
speech_synthesizer.speak_text_async("Hello, I am BearBuddy!").get()
