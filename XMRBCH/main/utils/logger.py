"""
JSON transaction log — a human-readable flat file recording every swap.
Each entry is appended as a JSON object on its own line (JSON Lines format),
so the file is easy to tail, grep, and import into a spreadsheet.
"""
import json
import os
from datetime import datetime, timezone
import config


def _log_path():
    return os.path.join(config.DATA_DIR, config.TRANSACTION_LOG_FILE)


def log_swap_created(swap):
    """Called when a new swap is initialised."""
    _append({
        "event": "swap_created",
        "swap_id": str(swap.swap_id),
        "order_number": swap.order_number,
        "direction": swap.direction,
        "deposit_address": swap.deposit_address,
        "receiving_address": swap.receiving_address,
        "deposit_amount_expected": str(swap.deposit_amount_expected),
        "rate": str(swap.rate),
        "expires_at": swap.expires_at.isoformat(),
        "timestamp": _now(),
    })


def log_deposit_received(swap):
    _append({
        "event": "deposit_received",
        "swap_id": str(swap.swap_id),
        "direction": swap.direction,
        "deposit_address": swap.deposit_address,
        "deposit_amount_received": str(swap.deposit_amount_received),
        "deposit_tx_hash": swap.deposit_tx_hash,
        "timestamp": _now(),
    })


def log_swap_complete(swap):
    _append({
        "event": "swap_complete",
        "swap_id": str(swap.swap_id),
        "direction": swap.direction,
        "from_currency": swap.from_currency(),
        "to_currency": swap.to_currency(),
        "deposit_address": swap.deposit_address,
        "receiving_address": swap.receiving_address,
        "deposit_amount_received": str(swap.deposit_amount_received),
        "send_amount": str(swap.send_amount),
        "rate": str(swap.rate),
        "deposit_tx_hash": swap.deposit_tx_hash,
        "send_tx_hash": swap.send_tx_hash,
        "duration_seconds": (
            (swap.completed_at - swap.created_at).total_seconds()
            if swap.completed_at else None
        ),
        "timestamp": _now(),
    })


def log_swap_failed(swap, reason=""):
    _append({
        "event": "swap_failed",
        "swap_id": str(swap.swap_id),
        "direction": swap.direction,
        "reason": reason or swap.notes,
        "timestamp": _now(),
    })


def log_deposit_swept(swap):
    _append({
        "event": "deposit_swept",
        "swap_id": str(swap.swap_id),
        "deposit_address": swap.deposit_address,
        "sweep_tx_hash": swap.sweep_tx_hash,
        "timestamp": _now(),
    })


def _now():
    return datetime.now(timezone.utc).isoformat()


def _append(entry):
    path = _log_path()
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
