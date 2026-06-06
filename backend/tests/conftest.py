import os

# config.py instantiates Settings() at import time, which requires PRINTER_HOST and
# either API_TOKEN or DISABLE_AUTH. CI has no .env file (it's gitignored), so set
# CI-safe defaults before any test module imports the app. setdefault means a real
# local .env / environment still wins.
os.environ.setdefault("PRINTER_HOST", "127.0.0.1")
os.environ.setdefault("DISABLE_AUTH", "true")
