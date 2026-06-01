"""
list_models.py — print the exact Gemini model IDs available to THIS project.

Run once after setup (or any time a model string is in doubt) to set
routing.model / routing.fallback_model in client_config.yaml correctly.
This retires the "is the model ID stale?" question per client.

    python list_models.py
"""
import os

from google import genai


def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    try:
        models = list(client.models.list())
    except Exception as e:
        raise SystemExit(f"Could not list models: {e}")

    tier, other = [], []
    for m in models:
        name = m.name.split("/")[-1]
        (tier if ("flash-lite" in name or "pro" in name) else other).append(name)

    print("Classification-tier models (use one of these for routing.model):")
    for n in sorted(tier):
        print(f"  - {n}")
    print("\nOther available models:")
    for n in sorted(other):
        print(f"  - {n}")
    print("\nNote: do NOT use '*-latest' or experimental IDs in production — "
          "they are unstable and rate-limited. Pin a stable, dated/GA string.")


if __name__ == "__main__":
    main()
