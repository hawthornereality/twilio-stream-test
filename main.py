from fastapi import FastAPI, WebSocket
import json
import base64
import os
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

app = FastAPI()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

async def transcribe_live(websocket: WebSocket):
    print("🔗 Connecting to Deepgram…")
    try:
        await websocket.accept()
        print("🔌 WebSocket connection from Twilio")
        
        # Initialize async Deepgram client
        dg = AsyncDeepgramClient(api_key=DEEPGRAM_API_KEY)
        conn = await dg.listen.v2.connect(
            model="nova-2-phonecall",
            language="en",
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            punctuate=True
        )

        # Define event handlers
        async def on_transcript(data):
            try:
                transcript = data.channel.alternatives[0].transcript
                if transcript:
                    print(f"🗣️ Transcript: {transcript}")
                    # TODO: Add lead qualification logic here
            except Exception as e:
                print(f"Transcript parse error: {e}")

        async def on_error(error):
            print(f"Deepgram error: {error}")

        # Register event handlers
        conn.on(EventType.MESSAGE, on_transcript)
        conn.on(EventType.ERROR, on_error)

        # Start listening
        await conn.start_listening()
        print("✅ Deepgram connected")

        # Handle Twilio WebSocket messages
        while True:
            try:
                msg = await websocket.receive_text()
                if not msg:
                    print("WebSocket closed by Twilio")
                    break
                data = json.loads(msg)
                event = data.get("event")
                print(f"Received Twilio event: {event}")
                if event == "media":
                    audio = base64.b64decode(data["media"]["payload"])
                    await conn.send(audio)
                elif event == "stop":
                    print("🏁 Call ended, closing Deepgram stream")
                    await conn.finish()
                    break
            except Exception as e:
                print(f"WebSocket message error: {e}")
                break

    except Exception as e:
        print(f"Deepgram connection error: {e}")
    finally:
        await conn.finish()
        await websocket.close()
        print("❌ Twilio connection closed")

@app.websocket("/media")
async def media(websocket: WebSocket):
    await transcribe_live(websocket)

@app.post("/twiml")
async def twiml():
    print("📞 Twilio hit /twiml")
    return {
        "xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Start><Stream url="wss://twilio-stream-test.onrender.com/media" track="both"/></Start>'
            '<Say>Hello! This is your AI bot for real estate leads. How can I help?</Say>'
            '<Pause length="10"/>'
            '<Redirect>/twiml</Redirect>'
            '</Response>'
        ),
        "headers": {"Content-Type": "text/xml"}
    }

@app.get("/")
async def home():
    return "Twilio ↔ Deepgram live stream active"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
