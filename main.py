from flask import Flask
from flask_sock import Sock
import json
import base64
import asyncio
import threading
import os
from deepgram import DeepgramClient, LiveTranscriptionEvents

app = Flask(__name__)
sock = Sock(app)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY") or "your_key_here"

def run_async(func):
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper

@run_async
async def transcribe_live(ws):
    print("🔗 Connecting to Deepgram…")
    dg = DeepgramClient(DEEPGRAM_API_KEY)
    conn = dg.listen.live.v("1")

    async def on_transcript(data):
        try:
            payload = json.loads(data)
            transcript = payload["channel"]["alternatives"][0]["transcript"]
            if transcript:
                print(f"🗣️ {transcript}")
        except Exception as e:
            print("parse error:", e)

    conn.on(LiveTranscriptionEvents.Transcript, on_transcript)

    options = {
        "model": "nova-2-phonecall",
        "language": "en",
        "encoding": "mulaw",
        "sample_rate": 8000,
        "punctuate": True,
    }

    await conn.start(options)

    while True:
        msg = ws.receive()
        if msg is None:
            break
        data = json.loads(msg)
        event = data.get("event")
        if event == "media":
            audio = base64.b64decode(data["media"]["payload"])
            await conn.send(audio)
        elif event == "stop":
            print("🏁 Call ended, closing Deepgram stream")
            await conn.finish()
            break

@sock.route("/media")
def media(ws):
    print("🔌 WebSocket connection from Twilio")
    threading.Thread(target=transcribe_live, args=(ws,)).start()
    while ws.receive() is not None:
        pass
    print("❌ Twilio connection closed")

@app.route("/")
def home():
    return "Twilio ↔ Deepgram live stream active"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
