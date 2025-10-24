import os, json, base64
import threading, asyncio
import websockets  # Deepgram uses WebSockets for streaming API
from flask import Flask, request
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

# Load environment variables (ensure DEEPGRAM_API_KEY is set in your Render env vars)
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("DEEPGRAM_API_KEY is not set in environment variables")

app = Flask(__name__)
sock = Sock(app)

@app.route("/voice", methods=["POST"])
def voice_webhook():
    """Twilio Voice webhook that returns TwiML to start the media stream."""
    response = VoiceResponse()
    # Instruct Twilio to connect the call’s audio to our /stream WebSocket
    connect = Connect()
    connect.stream(name="DeepgramStream", url=f"wss://{request.host}/stream", track="inbound")
    response.append(connect)
    # (You can use track="inbound" for caller’s audio only, or "both" with dual channels)
    return str(response)

# We will spawn a background thread running an asyncio loop for Deepgram WebSocket
audio_queue = None           # To queue audio bytes for Deepgram
deepgram_loop = None         # AsyncIO event loop for Deepgram streaming
deepgram_thread = None       # Thread running the Deepgram event loop

@sock.route("/stream")
def stream_route(ws):
    """WebSocket endpoint for Twilio to stream call audio."""
    global audio_queue, deepgram_loop, deepgram_thread

    # Initialize an asyncio loop and queue for this call
    audio_queue = asyncio.Queue()
    deepgram_loop = asyncio.new_event_loop()

    async def deepgram_worker():
        """Async task that connects to Deepgram and streams audio for transcription."""
        uri = (
            "wss://api.deepgram.com/v1/listen?"
            "encoding=mulaw&sample_rate=8000&channels=1"
        )
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        # Connect to Deepgram’s real-time transcription API via WebSocket
        async with websockets.connect(uri, extra_headers=headers) as dg_ws:
            # Task: send audio from the queue to Deepgram
            async def send_audio():
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        break  # No more audio
                    await dg_ws.send(chunk)
                # All audio sent; close Deepgram connection
                await dg_ws.close()

            # Task: receive transcripts from Deepgram
            async def receive_transcripts():
                async for msg in dg_ws:
                    # Deepgram sends JSON transcripts in text frames
                    data = json.loads(msg)
                    # When a transcript segment is finalized, print it out
                    if data.get("channel"):
                        text = data["channel"]["alternatives"][0].get("transcript")
                        if text:
                            print(f"Transcription: {text}")

            # Run send and receive tasks concurrently
            await asyncio.gather(send_audio(), receive_transcripts())

    # Start Deepgram worker in a background thread
    def run_deepgram_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(deepgram_worker())

    deepgram_thread = threading.Thread(target=run_deepgram_loop, args=(deepgram_loop,))
    deepgram_thread.daemon = True
    deepgram_thread.start()

    # Handle incoming messages from Twilio Media Stream
    while True:
        message = ws.receive()  # Receive a JSON-formatted string
        if message is None:
            break  # WebSocket closed
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            continue  # Skip if message is not valid JSON
        event = data.get("event")
        if event == "start":
            print(f"🔗 Twilio stream started (Call SID: {data['start'].get('callSid')})")
        elif event == "media":
            # Decode the base64-encoded audio chunk and send to Deepgram
            audio_chunk = base64.b64decode(data['media']['payload'])
            # Submit audio to the asyncio queue in the Deepgram thread
            asyncio.run_coroutine_threadsafe(audio_queue.put(audio_chunk), deepgram_loop)
        elif event == "stop":
            print("🚫 Twilio stream stopped")
            # Signal the Deepgram sender to stop and close
            asyncio.run_coroutine_threadsafe(audio_queue.put(None), deepgram_loop)
            break

    # End of Twilio stream; wait for Deepgram thread to finish cleanly
    if deepgram_thread and deepgram_thread.is_alive():
        deepgram_thread.join(timeout=5)
