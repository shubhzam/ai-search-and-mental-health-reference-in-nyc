"""Check API authentication and manifest model visibility without generating text."""

import json
import os
import ssl
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from urllib.parse import quote

import yaml
from dotenv import dotenv_values


PROVIDERS = {
    "anthropic": ("ANTHROPIC_API_KEY", "api.anthropic.com", "/v1/models/"),
    "openai": ("OPENAI_API_KEY", "api.openai.com", "/v1/models/"),
    "gemini": ("GEMINI_API_KEY", "generativelanguage.googleapis.com", "/v1beta/models/"),
}


def check_model(
    provider: str, model_id: str, api_key: str, tls: ssl.SSLContext
) -> str | None:
    _, host, path = PROVIDERS[provider]
    if provider == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    elif provider == "openai":
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        headers = {"x-goog-api-key": api_key}

    connection = HTTPSConnection(host, timeout=10, context=tls)
    try:
        connection.request("GET", path + quote(model_id, safe=""), headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            return f"HTTP {response.status}"
        metadata = json.loads(response.read())
    except (OSError, HTTPException, ValueError) as error:
        return type(error).__name__
    finally:
        connection.close()

    field, expected = ("name", f"models/{model_id}") if provider == "gemini" else ("id", model_id)
    if not isinstance(metadata, dict) or metadata.get(field) != expected:
        return "unexpected model metadata"
    return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dotenv = dotenv_values(root / ".env", interpolate=False)
    models = yaml.safe_load((root / "models.yaml").read_text(encoding="utf-8"))["models"]
    tls = ssl.create_default_context()
    system_certs = Path("/etc/ssl/cert.pem")
    if not tls.get_ca_certs() and system_certs.is_file():
        tls.load_verify_locations(cafile=system_certs)
    failed = False
    for provider, (key_name, _, _) in PROVIDERS.items():
        api_key = (os.environ.get(key_name, dotenv.get(key_name)) or "").strip()
        if not api_key:
            print(f"{provider}: {key_name} is missing")
            failed = True
            continue
        for model in models:
            if model["provider"] != provider:
                continue
            model_id = model["model_id"]
            error = check_model(provider, model_id, api_key, tls)
            if error is None:
                print(f"{provider} / {model_id}: OK")
            else:
                print(f"{provider} / {model_id}: FAILED ({error})")
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
