"""Einfache Template-Engine für Erebos Hidden Services.

Unterstützt NUR `{{ variable }}`-Ersetzung. Keine Schleifen, keine
Bedingungen, kein Code. Alle Variablen werden HTML-escaped (XSS-Schutz).

Beispiel:
    template = "<h1>Willkommen, {{ name }}!</h1>"
    html = render_template(template, {"name": "Alice"})
    # -> "<h1>Willkommen, Alice!</h1>"
"""

import html as _html
import re

# Regex für {{ variable }} — erlaubt Leerzeichen um den Namen
_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_template(template: str, context: dict) -> str:
    """Ersetzt {{ var }} in template durch context[var] (HTML-escaped).

    Unbekannte Variablen bleiben als {{ var }} stehen.
    """
    def _replace(match):
        key = match.group(1)
        if key in context:
            return _html.escape(str(context[key]), quote=True)
        return match.group(0)  # unbekannt → unverändert

    return _TEMPLATE_RE.sub(_replace, template)


def is_template(content: str) -> bool:
    """Prüft, ob ein String Template-Variablen enthält."""
    return bool(_TEMPLATE_RE.search(content))
