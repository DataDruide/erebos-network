"""Einfache Template-Engine für Erebos Hidden Services.

Unterstützt:
- `{{ variable }}` — Variablen-Ersetzung (HTML-escaped)
- `{{#items}}...{{/items}}` — Schleifen (Liste von Dicts)
- `{{#if var}}...{{/if}}` — Bedingungen (truthy)
- Verschachtelung von Schleifen und Bedingungen

KEIN Code, KEIN eval(). Nur sichere Variablen-Ersetzung.
"""

import html as _html
import re

# Regex für {{ variable }} — erlaubt Leerzeichen
_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# Regex für {{#section}}...{{/section}} — Schleifen und Bedingungen
_SECTION_RE = re.compile(
    r"\{\{#([a-zA-Z_][a-zA-Z0-9_]*)\}\}(.*?)\{\{/\1\}\}",
    re.DOTALL,
)


def render_template(template: str, context: dict) -> str:
    """Rendert ein Template mit Schleifen und Bedingungen."""
    if not isinstance(context, dict):
        return template

    # 1) Sections (Schleifen/Bedingungen) — rekursiv
    def _section_replace(match):
        key = match.group(1)
        inner = match.group(2)
        value = context.get(key)

        # Bedingung: truthy, aber keine Liste → inner einmal rendern
        if value is True:
            return render_template(inner, context)

        # Bedingung: falsy → leer
        if not value:
            return ""

        # Schleife: Liste von Dicts
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    # Kontext für dieses Item: item + parent (Fallback)
                    item_ctx = {**context, **item}
                    parts.append(render_template(inner, item_ctx))
                else:
                    # Einfacher Wert
                    parts.append(render_template(inner, {**context, ".": item}))
            return "".join(parts)

        # Dict → inner einmal mit dem Dict als Kontext
        if isinstance(value, dict):
            return render_template(inner, {**context, **value})

        return ""

    # 2) Sections rekursiv ersetzen (bis keine Änderung mehr)
    prev = None
    while prev != template:
        prev = template
        template = _SECTION_RE.sub(_section_replace, template)

    # 3) Variablen ersetzen
    def _var_replace(match):
        key = match.group(1)
        if key in context:
            return _html.escape(str(context[key]), quote=True)
        return match.group(0)  # unbekannt → unverändert

    return _VAR_RE.sub(_var_replace, template)


def is_template(content: str) -> bool:
    """Prüft, ob ein String Template-Variablen enthält."""
    return bool(_VAR_RE.search(content) or _SECTION_RE.search(content))
