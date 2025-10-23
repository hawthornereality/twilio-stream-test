from flask import Flask
from flask_sock import Sock
import json
import base64
from deepgram import Deepgram
import asyncio
import threading

app = Flask(__name__)
sock = Sock(app)

# Replace this with your real Deepgram API key
DEEPGRAM_API_KEY = "4e9337099bcbd8f3b0dd5bd5155aa4b04ed94dbb"

# Create the Deepgram client
dg_client = Deepgram(DEEPGRAM_API_KEY)

@app.route("/")
def home():
    return "Twilio -> Deepgram stream running"

def run_async(func):
    """Run async functions in a background thread."""
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper

@run_async
async def transcribe_live(ws):
    """Open Deepgram live connection and stream Twilio audio to it."""
    print("🔗 Connecting to Deepgram...")
    deepgram_socket = await dg_client.transcription.live(
        {
            "punctuate": True,
            "interim_results": False,
            "encoding": "mulaw",
            "sample_rate": 8000
        }
    )

    @deepgram_socket.on_transcript_received
    def on_transcript(data, **kwargs):
        try:
            sentence = data["channel"]["alternatives"][0]["transcript"]
            if sentence:
                print(f"🗣️ {sentence}")
        except Exception as e:
            print(f"Error parsing transcript: {e}")

    @deepgram_socket.on_close
    def on_close():
        print("❌ Deepgram connection closed")

    while True:
        message = ws.receive()
        if message is None:
            break
        data = json.loads(message)
        if data.get("event") == "media":
            audio = base64.b64decode(data["media"]["payload"])
            deepgram_socket.send(audio)
        elif data.get("event") == "stop":
            print("🏁 Call ended, closing Deepgram stream")
            await deepgram_socket.finish()
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
