# Skill: pantalla — actualizar el panel derecho de PiDashboard

Actualiza el panel derecho de la pantallita del Raspberry Pi escribiendo `display_state.json` de forma atómica.

## Cómo usarlo

```
/pantalla <qué mostrar>
```

Ejemplos:
- `/pantalla happy`
- `/pantalla warning`
- `/pantalla 😊`
- `/pantalla Hola Edgar`
- `/pantalla rocket "Lanzamiento" "Deploy exitoso"`

## Instrucciones para Claude

Cuando el usuario invoque este skill, interpreta su intención y ejecuta el script Python de abajo para escribir `display_state.json`.

### Reglas de interpretación

**Tipo `icon`** — úsalo cuando el usuario pida uno de estos nombres exactos (o sinónimos obvios):

| value | cuándo usarlo |
|-------|--------------|
| `happy` | feliz, contento, bien, ok-ánimo, 😊, 🙂 |
| `sad` | triste, mal, 😢, 😞 |
| `rocket` | rocket, lanzamiento, deploy, cohete, 🚀 |
| `warning` | warning, alerta, cuidado, ⚠️ |
| `ok` | ok, listo, hecho, ✅, check |
| `sleep` | dormir, inactivo, sleep, 😴 |
| `bitcoin` | bitcoin, btc, crypto, ₿ |
| `heart` | corazón, amor, love, ❤️ |

**Tipo `emoji`** — úsalo cuando el usuario pase un emoji literal que NO esté en la tabla de arriba.

**Tipo `text`** — úsalo cuando el usuario pase texto normal (no un nombre de icon ni un emoji).

### Parámetros opcionales

Después del valor principal el usuario puede especificar (en cualquier orden):
- `title="..."` — título del panel (por defecto: "Mood" para icons, "Emoji" para emojis, "Mensaje" para texto)
- `subtitle="..."` — subtítulo (por defecto: "Set from OpenClaw")

### Script Python a ejecutar

Sustituye `TYPE`, `VALUE`, `TITLE` y `SUBTITLE` según la interpretación, y ejecuta con el Bash tool:

```python
python3 - <<'PYEOF'
import json, os, tempfile
from datetime import datetime, timezone

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath("display_state.json")), "display_state.json")

payload = {
    "panel_right": {
        "type": "TYPE",
        "value": "VALUE",
        "title": "TITLE",
        "subtitle": "SUBTITLE"
    },
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "source": "openclaw"
}

dirname = os.path.dirname(STATE_PATH) or "."
fd, tmp = tempfile.mkstemp(prefix="display_state_", suffix=".tmp", dir=dirname)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)
    print(f"✓ Pantalla actualizada: type={payload['panel_right']['type']} value={payload['panel_right']['value']}")
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
PYEOF
```

### Ruta del archivo

El archivo `display_state.json` debe escribirse en el directorio de trabajo actual (donde está `app.py`). Si el usuario indica una ruta diferente, úsala. En el Raspberry Pi la ruta típica es `/home/neomano/pidashboard/display_state.json`.

### Verificación opcional

Si el usuario quiere confirmar que se aplicó, ejecuta:
```bash
curl -s http://127.0.0.1:3000/api/display-state | python3 -m json.tool
```

### Respuesta al usuario

Después de ejecutar, responde brevemente confirmando qué se mostró en pantalla. Ejemplo:
> ✓ Pantalla actualizada: `happy` (icon) — título "Mood"
