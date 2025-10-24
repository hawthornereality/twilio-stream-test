from flask import Flask
from flask_sock import Sock
import json
import base64
import asyncio
import os
from deepgram import DeepgramClient, LiveTranscriptionOptions

app = Flask(__name__)
sock = Sock(app)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

async def transcribe_live(ws):
    print("🔗 Connecting to Deepgram…")
    try:
        # Initialize Deepgram client
        dg = DeepgramClient(api_key=DEEPGRAM_API_KEY)
        conn = dg.listen.live.v("1")

        # Define event handlers
        async def on_transcript(data, **kwargs):
            try:
                transcript = data.channel.alternatives[0].transcript
                if transcript:
                    print(f"🗣️ Transcript: {transcript}")
                    # TODO: Add lead qualification logic here (e.g., LLM integration)
            except Exception as e:
                print(f"Transcript parse error: {e}")

        async def on_error(error, **kwargs):
            print(f"Deepgram error: {error}")

        # Register event handlers
        conn.on("transcript", on_transcript)
        conn.on("error", on_error)

        # Configure Deepgram options
        options = LiveTranscriptionOptions(
            model="nova-2-phonecall",
            language="en",
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            punctuate=True
        )

        # Start Deepgram connection
        await conn.start(options)
        print("✅ Deepgram connected")

        # Handle Twilio WebSocket messages
        while True:
            msg = await ws.receive()
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

    except Exception as e:
        print(f"Deepgram connection error: {e}")
    finally:
        await conn.finish()
        await ws.close()

@sock.route("/media")
async def media(ws):
    print("🔌 WebSocket connection from Twilio")
    try:
        await transcribe_live(ws)
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        print("❌ Twilio connection closed")
        await ws.close()

@app.route("/twiml", methods=["POST"])
def twiml():
    print("📞 Twilio hit /twiml")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        '<Start><Stream url="wss://twilio-stream-test.onrender.com/media" track="both"/></Start>'
        '<Say>Hello! This is your AI bot for real estate leads. How can I help?</Say>'
        '</Response>',
        200,
        {"Content-Type": "text/xml"},
    )

@app.route("/")
def home():
    return "Twilio ↔ Deepgram live stream active"

if __name__ == "__main__":
    app.run()
