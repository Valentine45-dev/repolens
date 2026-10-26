import os

DEBUG = True
# Deliberately hardcoded fake credential: the redaction and hardcoded-secret tests rely on it.
DB_PASSWORD = "fixture-not-a-real-password"
API_KEY = os.environ.get("API_KEY", "")
