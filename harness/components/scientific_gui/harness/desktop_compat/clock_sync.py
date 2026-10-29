"""Align the isolated guest clock without the SDK's GUI import delay."""
import json
import time


def _execute(transport, url, command, *, read_only=False):
    transport.bind(time.monotonic() + 15)
    transport.read_only = read_only
    try:
        reply = transport.post(url + "/execute", json={"command": command, "shell": False})
        reply.raise_for_status()
        result = reply.json()
        if result.get("status") != "success" or result.get("returncode") != 0:
            raise RuntimeError("Guest clock command failed")
        return result
    finally:
        transport.read_only = False


def synchronize_guest_clock(transport, url, tolerance=.5):
    # A single confirmed administrative mutation. Never repeat an uncertain date
    # command. Bypass the SDK's pyautogui preamble, which delays a stale target.
    target = time.time()
    _execute(transport, url, ["sudo", "-n", "date", "-u", "-s", "@"+format(target, ".6f")])
    samples = []
    for _ in range(5):
        before = time.time()
        result = _execute(transport, url, ["python3", "-c",
            "import time,json;print(json.dumps({'guest_seconds':time.time()}))"],
            read_only=True)
        after = time.time()
        guest = float(json.loads(result["output"])["guest_seconds"])
        # Guest sampling happens somewhere inside the complete host round trip.
        # Require the entire possible offset interval to satisfy the old gate.
        lower, upper = guest-after, guest-before
        sample = {"host_before": before, "host_after": after, "guest_seconds": guest,
                  "offset_lower": lower, "offset_upper": upper,
                  "within_tolerance": after >= before and lower >= -tolerance and upper <= tolerance}
        samples.append(sample)
        if sample["within_tolerance"]:
            return {"host_target_seconds": target, "samples": samples,
                    "gate_seconds_unchanged": tolerance, "scope": "trusted environment initialization only"}
    raise RuntimeError("Guest clock offset could not be bounded within 0.5 seconds")
