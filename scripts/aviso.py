"""Avisos Telegram del microservicio de vivienda.

Marca propia: el envío se hace desde el .env PROPIO de vivienda
(/home/deploy/vivienda-osint/.env), no desde el del radar. Si ese fichero no
existe (compatibilidad de arranque), cae al .env del radar y se loguea: el
objetivo es quitar esa dependencia, no esconderla.

Sin secretos en código: solo se leen los nombres de variable de los ficheros.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PROPIO = os.path.join(ROOT, ".env")                 # marca propia de vivienda
ENV_RADAR = "/home/deploy/hybrid-fimi-radar/.env"       # única dependencia externa (a eliminar)


def _cargar(path: str) -> dict[str, str]:
    """Devuelve {clave: valor} de un .env, sin comillas ni espacios colgantes."""
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for linea in fh:
                l = linea.strip()
                if not l or l.startswith("#") or "=" not in l:
                    continue
                k, v = l.split("=", 1)
                k = k.strip()
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                if k:
                    out[k] = v
    except OSError as e:
        print(f"[aviso] no se pudo leer {path}: {e}", file=sys.stderr)
    return out


def token_y_chat() -> tuple[str, str]:
    """Token y chat: .env propio de vivienda; si no existe, el del radar (transitorio)."""
    env = _cargar(ENV_PROPIO)
    if env:
        # deja claro de qué vive el aviso; que no avise en silencio sin token
        if not env.get("VIVIENDA_TELEGRAM_BOT_TOKEN") or not env.get("VIVIENDA_OWNER_CHAT"):
            print(f"[aviso] {ENV_PROPIO}: faltan claves Telegram (marca vivienda)",
                  file=sys.stderr)
        return (env.get("VIVIENDA_TELEGRAM_BOT_TOKEN", ""),
                env.get("VIVIENDA_OWNER_CHAT", ""))
    print(f"[aviso] sin .env propio: fallback al del radar ({ENV_RADAR})", file=sys.stderr)
    env = _cargar(ENV_RADAR)
    return (env.get("FIMI_TELEGRAM_BOT_TOKEN", ""),
            env.get("FIMI_OWNER_CHAT") or env.get("FIMI_TELEGRAM_CHAT_ID", ""))


def enviar(msg: str) -> bool:
    """Envía `msg` al owner. Devuelve True solo si el envío se confirmó (rc=200)."""
    token, chat = token_y_chat()
    if not token or not chat:
        print("[aviso] sin token/chat de Telegram: no se avisó (el log queda como aviso)",
              file=sys.stderr)
        return False
    data = json.dumps({"chat_id": chat, "text": msg}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] Telegram fallo: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    sys.exit(0 if enviar(" ".join(sys.argv[1:])) else 1)