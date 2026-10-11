"""Development server: python -m chaos_blackjack.web (production uses Gunicorn)."""
import os
from wsgiref.simple_server import make_server
from .server import create_app

if __name__ == "__main__":
    os.environ.setdefault("BLACKJACK_SECURE_COOKIE", "0")
    with make_server("127.0.0.1", int(os.environ.get("PORT", "8000")), create_app()) as server:
        print("Chaos Blackjack: http://127.0.0.1:8000")
        server.serve_forever()
