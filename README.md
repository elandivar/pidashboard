# PiDashboard: estado externo por JSON

Este `app.py` ahora puede leer un archivo JSON local para controlar el panel derecho de la pantalla.

## Archivo que lee el dashboard

Por defecto el dashboard lee:

```text
./display_state.json
```

es decir, un archivo llamado `display_state.json` en la misma carpeta donde está `app.py`.

También puedes cambiar la ruta con esta variable de entorno:

```bash
export PIDASHBOARD_STATE_FILE=/ruta/al/display_state.json
```

## Qué hace

El dashboard hace polling del JSON cada 2 segundos y actualiza el panel derecho.

La lectura es solo lectura desde el dashboard. La idea es que OpenClaw escriba el archivo y el dashboard lo consuma.

## Estructura del JSON

### Opción 1: iconos internos recomendados

```json
{
  "panel_right": {
    "type": "icon",
    "value": "happy",
    "title": "Mood",
    "subtitle": "Set from OpenClaw"
  },
  "updated_at": "2026-03-17T15:30:00Z",
  "source": "openclaw"
}
```

Valores soportados para `value` cuando `type` es `icon`:

- `rocket`
- `happy`
- `sad`
- `warning`
- `ok`
- `sleep`
- `bitcoin`
- `heart`

Esta es la opción recomendada porque no depende de las fuentes emoji del sistema.

### Opción 2: emoji literal

```json
{
  "panel_right": {
    "type": "emoji",
    "value": "😊",
    "title": "Emoji",
    "subtitle": "Sent from WhatsApp"
  },
  "updated_at": "2026-03-17T15:31:00Z",
  "source": "openclaw"
}
```

Nota: si la Raspberry o el navegador no soportan bien emojis, puede verse mal. Por eso la opción `icon` es mejor.

### Opción 3: texto grande

```json
{
  "panel_right": {
    "type": "text",
    "value": "Hola Edgar",
    "title": "Message",
    "subtitle": "From OpenClaw"
  },
  "updated_at": "2026-03-17T15:32:00Z",
  "source": "openclaw"
}
```

## Recomendación de concurrencia

No escribas el archivo final directamente.

Haz escritura atómica:

1. escribir a `display_state.json.tmp`
2. hacer flush + fsync
3. renombrar a `display_state.json`

En Linux, `os.replace()` dentro del mismo filesystem es atómico.

## Ejemplo en Python para OpenClaw

```python
import json
import os
import tempfile
from datetime import datetime, timezone

STATE_PATH = "/ruta/a/pidashboard/display_state.json"

payload = {
    "panel_right": {
        "type": "icon",
        "value": "happy",
        "title": "Mood",
        "subtitle": "Set from OpenClaw"
    },
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "source": "openclaw"
}

dirname = os.path.dirname(STATE_PATH) or "."
fd, tmp_path = tempfile.mkstemp(prefix="display_state_", suffix=".tmp", dir=dirname)

try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, STATE_PATH)
finally:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
```

## Ejemplo rápido desde bash

```bash
cat > display_state.json.tmp <<'EOF'
{
  "panel_right": {
    "type": "icon",
    "value": "happy",
    "title": "Mood",
    "subtitle": "Set manually"
  },
  "updated_at": "2026-03-17T15:35:00Z",
  "source": "manual"
}
EOF
mv display_state.json.tmp display_state.json
```

## API útil para depuración

El dashboard expone este endpoint para revisar qué estado está leyendo:

```text
/api/display-state
```

Ejemplo:

```bash
curl http://127.0.0.1:3000/api/display-state
```

## Instalación sugerida

Dentro de la carpeta `pidashboard`:

```bash
cp app.py /ruta/a/pidashboard/app.py
cp PIDASHBOARD_README.md /ruta/a/pidashboard/
```

Luego reinicia el servicio:

```bash
sudo systemctl restart dashboard
```

## Ejemplos de comandos que OpenClaw podría mapear

- "pon un emoji feliz en la pantalla" -> `type=icon`, `value=happy`
- "pon alerta en la pantalla" -> `type=icon`, `value=warning`
- "pon ok en la pantalla" -> `type=icon`, `value=ok`
- "muestra hola edgar" -> `type=text`, `value="Hola Edgar"`

## Archivos sugeridos en la carpeta pidashboard

- `app.py`
- `display_state.json`
- `PIDASHBOARD_README.md`

## Estado por defecto

Si `display_state.json` no existe o está malformado, el dashboard mostrará un estado por defecto y seguirá funcionando.
