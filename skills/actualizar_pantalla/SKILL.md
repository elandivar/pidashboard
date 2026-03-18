---
name: actualizar-pantalla
description: Actualiza el panel derecho del PiDashboard escribiendo display_state.json con un ícono, emoji o texto especificado por el usuario.
user-invocable: true
metadata: {"openclaw":{"emoji":"🖥️","requires":{"bins":["python3"],"os":["linux","darwin"]}}}
---

## When to Use

El usuario quiere mostrar algo en la pantallita del Raspberry Pi: un ícono de estado, un emoji o un mensaje de texto.

## Core Rules

1. Detecta automáticamente el tipo según el input: `icon` si coincide con la tabla, `emoji` si es un carácter emoji, `text` para cualquier otro texto.
2. Escribe el archivo de forma atómica (tempfile + os.replace) para evitar lecturas parciales.
3. La ruta por defecto es `./display_state.json`. Si el usuario indica otra ruta, úsala.
4. Confirma brevemente qué se mostró en pantalla al terminar.
5. Si el tipo es ambiguo, elige `icon` si hay un match cercano, si no pregunta.

## Íconos disponibles

| value | cuándo usarlo |
|-------|---------------|
| `happy` | feliz, bien, 😊 |
| `sad` | triste, mal, 😢 |
| `rocket` | rocket, deploy, lanzamiento, 🚀 |
| `warning` | alerta, cuidado, ⚠️ |
| `ok` | ok, listo, ✅ |
| `sleep` | dormir, inactivo, 😴 |
| `bitcoin` | bitcoin, btc, ₿ |
| `heart` | amor, corazón, ❤️ |

## Workflow

1. Interpreta el input del usuario y determina `type`, `value`, `title` y `subtitle`.
2. Ejecuta el script de `write.py` con los valores resueltos.
3. Responde con una confirmación de una línea.

Ver detalles de implementación en `write.py`.
