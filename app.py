"""Flask app entry point for `flask run`."""

from dotenv import load_dotenv
from api.generate import app

load_dotenv()

__all__ = ["app"]
