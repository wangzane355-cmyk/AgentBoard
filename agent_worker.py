"""Subprocess bridge: plain text on stdin/stdout, never prints credentials."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def api_reply(profile, prompt):
    key = os.environ.get(profile["key_env"])
    if not key:
        raise ValueError("API key environment variable is not set")
    payload = {"model": profile["model"], "messages": [{"role": "user", "content": prompt}], "stream": False}
    request = urllib.request.Request(profile["endpoint"], data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    # Do not forward bearer credentials to redirects or echo provider error bodies.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=1200) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Provider response is too large")
        reply = json.loads(raw)["choices"][0]["message"]["content"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Provider returned no text content")
        return reply
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Provider HTTP {exc.code}; response body omitted") from None
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError):
        raise ValueError("Provider request failed or response format is unsupported") from None


def main():
    profiles = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    profile = next(p for p in profiles if p["id"] == sys.argv[2] and p["enabled"])
    prompt = sys.stdin.buffer.read().decode("utf-8")
    if profile["kind"] == "mock":
        answer = "[SIMULATION / 本地模拟] No model or account was used. Received project context; no files were modified.\nAGENTBOARD_STATUS: DONE"
    else:
        answer = api_reply(profile, prompt)
    sys.stdout.buffer.write(answer.encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never include request payloads, headers, endpoint URLs or provider bodies.
        sys.stderr.write("Agent bridge failed; check endpoint, response format and credential environment. Provider details omitted.")
        sys.exit(1)
