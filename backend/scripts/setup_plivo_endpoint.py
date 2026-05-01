"""One-time Plivo SIP Endpoint setup.

For demos that don't have a rented DID (e.g. India-region accounts pre-KYC),
a Plivo SIP Endpoint lets you reach the agent via a SIP softphone (Linphone,
Zoiper, etc.) without needing a phone number. The Endpoint binds to the
same Application that an inbound DID would, so the answer_url / hangup_url
flow is identical — you just dial a SIP URI instead of a phone number.

Idempotent. Re-running fetches the existing Application/Endpoint rather than
creating duplicates. Generates a random password the first time the Endpoint
is created and prints it; on subsequent runs the existing endpoint is reused
(password is not re-printed since Plivo doesn't expose stored passwords —
re-run with ``--rotate-password`` to set a new one if you've lost it).

Usage::

    cd backend && python -m scripts.setup_plivo_endpoint
    cd backend && python -m scripts.setup_plivo_endpoint --rotate-password
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys

import plivo
from plivo.exceptions import AuthenticationError, PlivoRestError

from app.config import settings


APP_NAME = "agent-studio"
ENDPOINT_USERNAME = "agentstudio"  # alphanumeric only — Plivo rejects hyphens
ENDPOINT_ALIAS = "agent-studio-demo"


def _random_password(length: int = 24) -> str:
    """Plivo passwords: alphanumeric, no special chars (their validator rejects)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _ensure_application(client: plivo.RestClient) -> str:
    """Find or create the agent-studio Application; return its app_id."""
    base = settings.PUBLIC_API_URL.rstrip("/")
    answer_url = f"{base}/api/v1/webhooks/voice/incoming"
    hangup_url = f"{base}/api/v1/webhooks/voice/status"

    try:
        apps = client.applications.list()
    except AuthenticationError:
        sys.exit("Plivo auth failed — check PLIVO_AUTH_ID / PLIVO_AUTH_TOKEN in backend/.env.")
    except PlivoRestError as e:
        sys.exit(f"Plivo API error listing applications: {e}")

    existing = next(
        (a for a in apps if getattr(a, "app_name", None) == APP_NAME),
        None,
    )

    try:
        if existing:
            client.applications.update(
                existing.app_id,
                answer_url=answer_url, answer_method="POST",
                hangup_url=hangup_url, hangup_method="POST",
            )
            print(f"Updated Application: {existing.app_id}")
            return existing.app_id

        app = client.applications.create(
            app_name=APP_NAME,
            answer_url=answer_url, answer_method="POST",
            hangup_url=hangup_url, hangup_method="POST",
        )
        print(f"Created Application: {app.app_id}")
        return app.app_id
    except PlivoRestError as e:
        sys.exit(f"Plivo API error creating/updating Application: {e}")


def _ensure_endpoint(
    client: plivo.RestClient,
    app_id: str,
    *,
    rotate_password: bool,
) -> tuple[str, str, str | None]:
    """Find or create the agent-studio SIP Endpoint.

    **Plivo gotcha:** the SDK's ``endpoints.create(username=...)`` doesn't store
    your username verbatim — Plivo appends a random numeric suffix for global
    uniqueness ("agentstudio" → "agentstudio10146403989399950706519"). The
    suffixed form is what Linphone must register with. We match existing
    endpoints by ``alias`` (which we control) rather than ``username``.

    Returns ``(endpoint_id, actual_username, password_or_None)``. password is
    non-None only when we just created the endpoint (or rotated it) — Plivo
    doesn't return stored passwords on subsequent reads.
    """
    try:
        endpoints_resp = client.endpoints.list()
    except PlivoRestError as e:
        sys.exit(f"Plivo API error listing endpoints: {e}")

    objects = getattr(endpoints_resp, "objects", None) or []
    existing = next(
        (e for e in objects if getattr(e, "alias", None) == ENDPOINT_ALIAS),
        None,
    )

    if existing and not rotate_password:
        try:
            client.endpoints.update(existing.endpoint_id, app_id=app_id)
        except PlivoRestError as e:
            print(f"Warning: failed to refresh endpoint binding: {e}")
        print(f"Reusing existing Endpoint: {existing.endpoint_id}")
        return existing.endpoint_id, existing.username, None

    password = _random_password()

    if existing and rotate_password:
        try:
            client.endpoints.update(
                existing.endpoint_id,
                password=password, app_id=app_id,
            )
        except PlivoRestError as e:
            sys.exit(f"Plivo API error rotating Endpoint password: {e}")
        print(f"Rotated password on existing Endpoint: {existing.endpoint_id}")
        return existing.endpoint_id, existing.username, password

    try:
        endpoint = client.endpoints.create(
            username=ENDPOINT_USERNAME,
            password=password,
            alias=ENDPOINT_ALIAS,
            app_id=app_id,
        )
    except PlivoRestError as e:
        sys.exit(f"Plivo API error creating Endpoint: {e}")
    print(f"Created Endpoint: {endpoint.endpoint_id}")
    # Read back the assigned username (Plivo appends a suffix).
    full = client.endpoints.get(endpoint.endpoint_id)
    return endpoint.endpoint_id, full.username, password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rotate-password",
        action="store_true",
        help="Set a new random password on the Endpoint (use if you've lost the original).",
    )
    args = parser.parse_args()

    if not (settings.PLIVO_AUTH_ID and settings.PLIVO_AUTH_TOKEN):
        sys.exit("PLIVO_AUTH_ID / PLIVO_AUTH_TOKEN not configured. Set them in backend/.env.")
    if not settings.PUBLIC_API_URL or settings.PUBLIC_API_URL.startswith("http://localhost"):
        sys.exit(
            "PUBLIC_API_URL is unset or points at localhost. "
            "Plivo can't reach localhost — set it to your public ngrok URL first."
        )

    try:
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
    except Exception as e:
        sys.exit(f"Failed to initialise Plivo client: {e}")

    app_id = _ensure_application(client)
    endpoint_id, actual_username, password = _ensure_endpoint(
        client, app_id, rotate_password=args.rotate_password,
    )

    sip_uri = f"sip:{actual_username}@phone.plivo.com"

    print("\n" + "=" * 60)
    print("Plivo SIP Endpoint ready for demo")
    print("=" * 60)
    print(f"Set in backend/.env:")
    print(f"  PLIVO_APPLICATION_ID={app_id}")
    print()
    print("Configure your SIP softphone (Linphone / Zoiper / etc.) with:")
    print(f"  SIP URI:    {sip_uri}")
    print(f"  Username:   {actual_username}")
    print(f"  Domain:     phone.plivo.com")
    if password:
        print(f"  Password:   {password}    ← SAVE THIS, Plivo doesn't expose it again")
    else:
        print(f"  Password:   (unchanged from previous setup)")
        print(f"              Re-run with --rotate-password if you've lost it.")
    print()
    print("NOTE: Plivo appends a numeric suffix to the username on creation —")
    print(f"  the actual SIP username is '{actual_username}', NOT just '{ENDPOINT_USERNAME}'.")
    print()
    print("Demo flow:")
    print("  1. Open Linphone, add a SIP account with the credentials above.")
    print("  2. Once registered, dial the SIP URI from inside Linphone.")
    print("  3. Plivo routes the call through your Application's answer_url —")
    print("     the same flow a real phone call to a DID would take.")
    print("=" * 60)


if __name__ == "__main__":
    main()
