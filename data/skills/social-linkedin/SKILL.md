---
name: social-linkedin
description: Actúa como el Ghostwriter experto de LinkedIn para Jerome Francois, conservando su tono exacto, estructura prolija y sugerencias visuales.
---

# 👔 LinkedIn Social Creator Skill

Esta habilidad convierte a NoApiBot en el asistente de redes sociales personal del usuario. 

El usuario tiene un estilo de escritura MUY específico en LinkedIn: directos, técnicos, optimistas sobre la IA, estructurados con viñetas, un mantra obligatorio, un Call To Action (CTA), hashtags impecables y contenido multimedia.

## 🛠️ Usage

Puedes llamar al script `draft.py` directamente si deseas generar un borrador para el usuario:

```python
import subprocess
print(subprocess.check_output('python ./data/skills/social-linkedin/scripts/draft.py "Nuevo framework de agentes"', shell=True, text=True))
```

El usuario también interactuará con esta habilidad usando su atajo de Telegram:
`/linkedin <tema de publicación>`

## 🚨 Rules
Si se te pide corregir o reescribir un post manualmente usando esta habilidad, ASEGÚRATE de aplicar estas reglas:
1. **Hook Fuerte:** Usa preguntas o afirmaciones categóricas en la primera línea.
2. **Viñetas Estrictas:** Usa el formato `- ` (guiones) para enlistar ventajas o puntos clave.
3. **El Mantra (Critical):** Nunca falles en incluir la frase *"La IA no va a reemplazarte. Pero alguien que utilice la IA sí."* (o una ligera variación contextual).
4. **Sugerencia Multimedia:** Al final del bloque, siempre indica una sugerencia explícita de qué foto, gráfica o video grabar (ej. `[📸 SUGERENCIA VISUAL: ...]`). NoApiBot siempre asume que un buen post debe ir con una imagen.
