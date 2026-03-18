#!/usr/bin/env python3
"""
Escritura atómica de display_state.json para PiDashboard.

Uso:
    python3 write.py <type> <value> [title] [subtitle] [state_path]

    type     : icon | emoji | text
    value    : nombre del ícono, carácter emoji, o texto a mostrar
    title    : (opcional) título del panel  — default: "Mood"
    subtitle : (opcional) subtítulo         — default: "Set from OpenClaw"
    path     : (opcional) ruta al archivo   — default: ./display_state.json
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

def write_state(type_, value, title="Mood", subtitle="Set from OpenClaw", path="display_state.json"):
    payload = {
        "panel_right": {
            "type": type_,
            "value": value,
            "title": title,
            "subtitle": subtitle,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "openclaw",
    }

    state_path = os.path.abspath(path)
    dirname = os.path.dirname(state_path)

    fd, tmp = tempfile.mkstemp(prefix="display_state_", suffix=".tmp", dir=dirname)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, state_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    print(f"✓ Pantalla actualizada → type={type_} value={value!r} title={title!r}")
    return payload


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        print("Uso: python3 write.py <type> <value> [title] [subtitle] [path]")
        sys.exit(1)

    write_state(
        type_    = args[0],
        value    = args[1],
        title    = args[2] if len(args) > 2 else "Mood",
        subtitle = args[3] if len(args) > 3 else "Set from OpenClaw",
        path     = args[4] if len(args) > 4 else "display_state.json",
    )
