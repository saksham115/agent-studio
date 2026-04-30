"""One-time Plivo Application setup.

Creates (or updates) a Plivo Application named ``agent-studio`` with the
``answer_url`` and ``hangup_url`` derived from PUBLIC_API_URL. Lists DIDs on
the account and binds the (only) DID to the Application if exactly one
unbound number exists.

Idempotent: re-runs update the existing Application rather than creating a
duplicate. Run after ``alembic upgrade head`` in production; safe to re-run
whenever PUBLIC_API_URL changes (e.g. ngrok URL rotated).

Usage::

    cd backend && python -m scripts.setup_plivo_app

Output prints the ``application_id``; copy it into ``backend/.env`` as
``PLIVO_APPLICATION_ID``.
"""

from __future__ import annotations

import sys

import plivo
from plivo.exceptions import AuthenticationError, PlivoRestError

from app.config import settings


def main() -> None:
    if not (settings.PLIVO_AUTH_ID and settings.PLIVO_AUTH_TOKEN):
        sys.exit(
            "PLIVO_AUTH_ID / PLIVO_AUTH_TOKEN not configured. "
            "Set them in backend/.env."
        )
    if not settings.PUBLIC_API_URL or settings.PUBLIC_API_URL.startswith("http://localhost"):
        sys.exit(
            "PUBLIC_API_URL is unset or points at localhost. "
            "Set it to your public ngrok / production URL before running."
        )

    try:
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
    except Exception as e:
        sys.exit(f"Failed to initialise Plivo client: {e}")

    base = settings.PUBLIC_API_URL.rstrip("/")
    answer_url = f"{base}/api/v1/webhooks/voice/incoming"
    hangup_url = f"{base}/api/v1/webhooks/voice/status"
    app_name = "agent-studio"

    # Find or create the Application.
    try:
        apps = client.applications.list()
    except AuthenticationError:
        sys.exit("Plivo auth failed — check PLIVO_AUTH_ID / PLIVO_AUTH_TOKEN.")
    except PlivoRestError as e:
        sys.exit(f"Plivo API error listing applications: {e}")

    existing = next(
        (a for a in apps if getattr(a, "app_name", None) == app_name),
        None,
    )

    try:
        if existing:
            client.applications.update(
                existing.app_id,
                answer_url=answer_url, answer_method="POST",
                hangup_url=hangup_url, hangup_method="POST",
            )
            app_id = existing.app_id
            print(f"Updated existing Application: {app_id}")
        else:
            app = client.applications.create(
                app_name=app_name,
                answer_url=answer_url, answer_method="POST",
                hangup_url=hangup_url, hangup_method="POST",
            )
            app_id = app.app_id
            print(f"Created Application: {app_id}")
    except PlivoRestError as e:
        sys.exit(f"Plivo API error creating/updating application: {e}")

    print(f"  answer_url = {answer_url}")
    print(f"  hangup_url = {hangup_url}")
    print(f"\nSet in backend/.env:\n  PLIVO_APPLICATION_ID={app_id}\n")

    # List rented DIDs and offer to bind.
    try:
        nums_resp = client.numbers.list()
    except PlivoRestError as e:
        print(f"Warning: could not list numbers: {e}")
        return

    objects = getattr(nums_resp, "objects", None) or []
    if not objects:
        print(
            "No DIDs rented yet. Rent one in the Plivo console "
            "(India landline, e.g. 022 / 080 series), then re-run."
        )
        return

    print("Rented DIDs:")
    for n in objects:
        bound = getattr(n, "application", None) or "(unbound)"
        print(f"  {n.number}  →  {bound}")

    unbound = [n for n in objects if not getattr(n, "application", None)]
    if len(objects) == 1 and unbound:
        n = objects[0]
        try:
            client.numbers.update(n.number, app_id=app_id)
            print(f"\nBound {n.number} → Application {app_id}.")
        except PlivoRestError as e:
            print(
                f"\nCould not auto-bind {n.number}: {e}\n"
                "Bind manually in Plivo console (Numbers → click the number "
                f"→ Application → select '{app_name}')."
            )
    elif len(objects) > 1:
        print(
            f"\nMultiple DIDs rented; bind each manually in Plivo console "
            f"(Application → '{app_name}'). Auto-bind only fires when there's "
            "exactly one unbound DID."
        )


if __name__ == "__main__":
    main()
