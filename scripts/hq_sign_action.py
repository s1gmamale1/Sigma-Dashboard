#!/usr/bin/env python3
"""Mint an X-Sigma-Signoff token for ONE HQ control action (high-friction gate).

The signing secret is read from the environment only — never pass it on argv.
Each token is bound to the exact action + target args + a single-use nonce and
expires fast (default 120s). The dashboard cannot mint these itself.

Usage:
    SIGMA_HQ_ACTION_SECRET=... python scripts/hq_sign_action.py create_task '{"title":"ship it"}'
    SIGMA_HQ_ACTION_SECRET=... python scripts/hq_sign_action.py stop_pane '{"sessionId":"abc"}' --ttl 60

Then POST it:
    curl -X POST .../api/v1/hq/actions/create_task \
      -H "Authorization: Bearer <admin>" -H "X-Sigma-Signoff: <token>" \
      -d '{"target": {"title":"ship it"}, "dry_run": true}'
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.hq.action_auth import mint_signoff  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Mint an HQ action signoff token.")
    ap.add_argument("action", help="action name (e.g. create_task, stop_pane)")
    ap.add_argument("target", help="JSON object of the action's target args")
    ap.add_argument("--ttl", type=int, default=120, help="token lifetime in seconds (default 120)")
    ap.add_argument("--nonce", default=None, help="explicit nonce (default: derived, single-use)")
    args = ap.parse_args()

    secret = os.environ.get("SIGMA_HQ_ACTION_SECRET", "")
    if not secret:
        print("ERROR: set SIGMA_HQ_ACTION_SECRET in the environment (never on argv).", file=sys.stderr)
        return 2
    try:
        target = json.loads(args.target)
    except json.JSONDecodeError as exc:
        print(f"ERROR: target is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(target, dict):
        print("ERROR: target must be a JSON object.", file=sys.stderr)
        return 2

    print(mint_signoff(secret, args.action, target, ttl_seconds=args.ttl, nonce=args.nonce))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
