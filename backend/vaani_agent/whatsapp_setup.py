"""Check (and fix) the Meta-side WhatsApp setup, instead of hunting through the dashboard.

    python -m vaani_agent.whatsapp_setup --waba 986368780577364 \\
        --callback https://<your-api>/webhooks/whatsapp            # status only
    python -m vaani_agent.whatsapp_setup ... --apply                # also fix it

--apply makes two changes on your Meta app:
  1. subscribes the app's WhatsApp webhook to the "messages" field, at --callback
     (Meta immediately re-verifies the URL with WHATSAPP_VERIFY_TOKEN), and
  2. connects your WhatsApp Business Account (--waba, "Messaging account ID")
     to the app, so its messages are delivered to the webhook.
Uses WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET and WHATSAPP_VERIFY_TOKEN from .env.
"""

import argparse
import sys

import httpx

from vaani_agent.config import get_agent_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--waba", required=True, help="WhatsApp Business Account ID (Messaging account ID)"
    )
    parser.add_argument("--callback", required=True, help="https://<your-api>/webhooks/whatsapp")
    parser.add_argument("--apply", action="store_true", help="make the changes, not just report")
    args = parser.parse_args()

    s = get_agent_settings()
    if not (s.whatsapp_access_token and s.whatsapp_app_secret and s.whatsapp_verify_token):
        sys.exit(
            "Set WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET and WHATSAPP_VERIFY_TOKEN in .env first."
        )
    graph = f"https://graph.facebook.com/{s.whatsapp_graph_version}"

    with httpx.Client(timeout=30) as h:
        app = h.get(f"{graph}/app", params={"access_token": s.whatsapp_access_token}).json()
        if "error" in app:
            sys.exit(
                f"Access token rejected: {app['error'].get('message')} (tokens from 'Try it out' last 24 h)"
            )
        app_id = app["id"]
        app_token = f"{app_id}|{s.whatsapp_app_secret}"

        def status() -> tuple[bool, bool]:
            subs = h.get(
                f"{graph}/{app_id}/subscriptions", params={"access_token": app_token}
            ).json()
            if "error" in subs:
                sys.exit(f"App secret rejected: {subs['error'].get('message')}")
            waba_sub = next(
                (x for x in subs.get("data", []) if x.get("object") == "whatsapp_business_account"),
                {},
            )
            fields = [f["name"] for f in waba_sub.get("fields", [])]
            apps = h.get(
                f"{graph}/{args.waba}/subscribed_apps",
                params={"access_token": s.whatsapp_access_token},
            ).json()
            connected = [
                a.get("whatsapp_business_api_data", {}).get("id") for a in apps.get("data", [])
            ]
            messages_on = "messages" in fields and waba_sub.get("callback_url") == args.callback
            print(f"App: {app.get('name')} ({app_id})")
            print(f"  webhook URL: {waba_sub.get('callback_url') or '(none)'}")
            print(
                f"  'messages' switched on at that URL: {'yes' if messages_on else 'NO'}  (fields: {fields or 'none'})"
            )
            print(
                f"  WhatsApp account {args.waba} connected to this app: {'yes' if app_id in connected else 'NO'}"
            )
            return messages_on, app_id in connected

        messages_on, connected = status()
        if messages_on and connected:
            print(
                "All set: messages to your WhatsApp number will reach Vaani (once the app is published)."
            )
            return
        if not args.apply:
            print("\nRun again with --apply to fix the items marked NO.")
            return

        if not messages_on:
            r = h.post(
                f"{graph}/{app_id}/subscriptions",
                data={
                    "object": "whatsapp_business_account",
                    "callback_url": args.callback,
                    "verify_token": s.whatsapp_verify_token,
                    "fields": "messages",
                    "access_token": app_token,
                },
            ).json()
            print(
                "Switching on 'messages':",
                "done" if r.get("success") else r.get("error", {}).get("message"),
            )
        if not connected:
            r = h.post(
                f"{graph}/{args.waba}/subscribed_apps",
                data={"access_token": s.whatsapp_access_token},
            ).json()
            print(
                "Connecting the WhatsApp account:",
                "done" if r.get("success") else r.get("error", {}).get("message"),
            )
        print()
        status()


if __name__ == "__main__":
    main()
