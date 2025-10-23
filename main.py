from flask import Flask
from flask_sock import Sock
import json

app = Flask(__name__)
sock = Sock(app)

@app.route("/")
def home():
    return "Twilio AI Stream Test Running"

# WebSocket endpoint for Twilio Media Streams
@sock.route("/media")
def media(ws):
    print("🔌 WebSocket connection received from Twilio")
    while True:
        try:
            message = ws.receive()
            if message is None:
                print("❌ Connection closed by Twilio")
                break

            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                print("📞 Call started")
            elif event == "media":
                print("🎧 Receiving audio chunk")
            elif event == "stop":
                print("🏁 Call ended")

        except Exception as e:
            print(f"⚠️ Error: {e}")
            break

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
