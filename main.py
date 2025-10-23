from flask import Flask
from flask_sock import Sock
import json
import base64
from deepgram_sdk import DeepgramClient, LiveTranscriptionEvents
import asyncio
import threading

app = Flask(__name__)
sock = Sock(app)

# Replace with your real Deepgram API key
DEEPGRAM_API_KEY = "4e9337099bcbd8f3b0dd5bd5155aa4b04ed94dbb"

def run_async(func):
    """Run async functions in a background thread."""
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper

@run_async
async def transcribe_live(ws):
    """Connect to Deepgram and stream Twilio audio for transcription."""
    print("🔗 Connecting to Deepgram...")
    dg = DeepgramClient(DEEPGRAM_API_KEY)

    # Start a live transcription connection
    dg_connection = dg.listen.live.v("1")
    options = {
        "model": "nova-2-phonecall",
        "language": "en",
        "encoding": "mulaw",
        "sample_rate": 8000,
        "punctuate": True,
        "interim_results": False
    }

    async def on_transcript(event):
        try:
            data = json.loads(event)
            transcript = data["channel"]["alternatives"][0]["transcript"]
            if transcript:
                print(f"🗣️ {transcript}")
        except Exception as e:
            print(f"Error parsing transcript: {e}")

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)

    await dg_connection.start(options)

    while True:
        msg = ws.receive()
        if msg is None:
            break
        data = json.loads(msg)
        if data.get("event") == "media":
            audio = base64.b64decode(data["media"]["payload"])
            await dg_connection.send(audio)
        elif data.get("event") == "stop":
            print("🏁 Call ended, closing Deepgram stream")
            await dg_connection.finish()
            break

@sock.route("/media")
def media(ws):
    print("🔌 WebSocket connection from Twilio")
    threading.Thread(target=transcribe_live, args=(ws,)).start()
    while True:
        msg = ws.receive()
        if msg is None:
            break
    print("❌ Twilio connection closed")

@app.route("/")
def home():
    return "Twilio -> Deepgram stream running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
