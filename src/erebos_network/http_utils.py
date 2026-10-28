"""HTTP-Hilfsfunktionen: Response-Builder + Request-Parser."""


def http_response(status: int, content_type: str, body: bytes,
                  location: str = "", set_cookie: str = "",
                  extra_headers: str = "") -> bytes:
    reason = {200: "OK", 302: "Found", 403: "Forbidden", 404: "Not Found",
              413: "Payload Too Large", 429: "Too Many Requests",
              500: "Internal Server Error"}.get(status, "OK")
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
    )
    if location:
        headers += f"Location: {location}\r\n"
    if set_cookie:
        headers += f"Set-Cookie: {set_cookie}\r\n"
    if extra_headers:
        # Rohe Header, bereits mit \r\n terminiert
        headers += extra_headers
    # Security Headers (OWASP A05:2025 Security Misconfiguration)
    headers += (
        "X-Content-Type-Options: nosniff\r\n"
        "X-Frame-Options: DENY\r\n"
        "Referrer-Policy: no-referrer\r\n"
        "Permissions-Policy: geolocation=(), microphone=(), camera=()\r\n"
        # CSP: kein externes Script, kein Inline-Script, nur eigene Styles
        # und Inline-Styles (die Templates nutzen style="...")
        "Content-Security-Policy: default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "form-action 'self'; "
        "frame-ancestors 'none'\r\n"
    )
    headers += "Connection: close\r\n\r\n"
    return headers.encode("ascii") + body


def parse_http_request(data: bytes) -> tuple:
    """Parst einen rohen HTTP-Request.

    Returns:
        (method, path, headers_dict, body_bytes)
    """
    if not data:
        return ("GET", "/", {}, b"")
    if b"\r\n\r\n" in data:
        head, body = data.split(b"\r\n\r\n", 1)
    else:
        head, body = data, b""
    lines = head.split(b"\r\n")
    if not lines:
        return ("GET", "/", {}, b"")
    request_line = lines[0].decode("utf-8", "replace")
    parts = request_line.split(" ")
    method = parts[0] if parts else "GET"
    target = parts[1] if len(parts) > 1 else "/"
    path = target.split("?", 1)[0] or "/"
    headers = {}
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            headers[k.decode("ascii", "replace").strip().lower()] = v.decode(
                "utf-8", "replace"
            ).strip()
    return (method, path, headers, body)


# ============================================================
# Key-Rotation: Bestaetigungsseite + POST-Handler
# ============================================================

