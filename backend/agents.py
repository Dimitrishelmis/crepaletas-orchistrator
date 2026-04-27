import os
from openai import OpenAI
import subprocess
import requests

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
DEFAULT_MODEL = "gemma3:latest"


def check_ollama():
    response = requests.get(OLLAMA_TAGS_URL, timeout=10)
    response.raise_for_status()
    data = response.json()

    return [
        model.get("name", "unknown")
        for model in data.get("models", [])
    ]


def generate_with_ollama(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 120):
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False
        },
        timeout=timeout
    )

    response.raise_for_status()
    data = response.json()

    return data.get("response", "No response from Ollama.")

def generate_with_openai(prompt: str, model: str = "gpt-4.1-mini", timeout: int = 60):
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model,
        input=prompt,
        timeout=timeout
    )

    return response.output_text
def looks_like_bad_greek(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return True

    bad_signals = [
        "CAPTION:",
        "HASHTAGS:",
        "CALL TO ACTION:",
        "STORY IDEA:",
        "SUGGESTED VISUAL:",
        "Crepaleta is",
        "filled waffle",
        "No response",
    ]

    greek_letters = sum(1 for ch in text if "α" <= ch.lower() <= "ω")
    total_letters = sum(1 for ch in text if ch.isalpha())

    if total_letters > 0 and greek_letters / total_letters < 0.45:
        return True

    return any(signal in text for signal in bad_signals)

def check_openclaw():
    result = subprocess.run(
        ["openclaw", "--help"],
        capture_output=True,
        text=True,
        timeout=10
    )

    output = result.stdout or result.stderr or "OpenClaw returned no output."

    return {
        "returncode": result.returncode,
        "output": output[:4000]
    }


def openclaw_status():
    result = subprocess.run(
        ["openclaw", "status"],
        capture_output=True,
        text=True,
        timeout=20
    )

    output = result.stdout or result.stderr or "OpenClaw returned no output."

    return {
        "returncode": result.returncode,
        "output": output[:4000]
    }
