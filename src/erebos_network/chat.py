"""In-Memory Chat-State fuer Erebos Network.

Verwaltet:
- Rooms (id -> {created, clients, messages, random})
- Cookie -> room_id (welcher Client ist in welchem Raum)
- Random-Queue (Cookies, die auf einen Match warten)

Persistenz: KEINE. Bei Neustart des Hidden-Service sind alle Chats weg.
Fuer einen Prototyp akzeptabel.
"""

import secrets
import time

# room_id -> {"created": ts, "clients": set(cookie), "messages": [...], "random": bool}
_ROOMS: dict[str, dict] = {}

# cookie -> room_id
_CLIENT_ROOM: dict[str, str] = {}

# Random-Queue: Liste von Cookies, die auf Match warten
_RANDOM_QUEUE: list[str] = []


def create_room(random: bool = False) -> str:
    """Erzeugt einen neuen Raum, gibt room_id (8 Hex) zurueck."""
    room_id = secrets.token_hex(4)
    _ROOMS[room_id] = {
        "created": time.time(),
        "clients": set(),
        "messages": [],
        "random": random,
    }
    return room_id


def room_exists(room_id: str) -> bool:
    return room_id in _ROOMS


def join_room(room_id: str, cookie: str) -> bool:
    """Client tritt Raum bei. False, wenn Raum nicht existiert."""
    if room_id not in _ROOMS:
        return False
    _ROOMS[room_id]["clients"].add(cookie)
    _CLIENT_ROOM[cookie] = room_id
    return True


def leave_room(cookie: str) -> None:
    room_id = _CLIENT_ROOM.pop(cookie, None)
    if room_id and room_id in _ROOMS:
        _ROOMS[room_id]["clients"].discard(cookie)


def current_room(cookie: str) -> str | None:
    return _CLIENT_ROOM.get(cookie)


def send_message(room_id: str, cookie: str, text: str) -> bool:
    if room_id not in _ROOMS:
        return False
    text = (text or "").strip()
    if not text:
        return False
    _ROOMS[room_id]["messages"].append({
        "ts": time.time(),
        "from": cookie,
        "text": text[:2000],  # Laengenlimit
    })
    return True


def get_messages(room_id: str, since: float = 0.0) -> list[dict]:
    if room_id not in _ROOMS:
        return []
    return [m for m in _ROOMS[room_id]["messages"] if m["ts"] > since]


def random_match(cookie: str) -> dict:
    """Matchmaking.

    Returns:
        {"matched": room_id}  -> Match gefunden (oder schon im Random-Raum)
        {"waiting": True}     -> in Queue
    """
    # Schon in einem Random-Raum?
    existing = _CLIENT_ROOM.get(cookie)
    if existing and _ROOMS.get(existing, {}).get("random"):
        return {"matched": existing}

    # Jemand wartet?
    while _RANDOM_QUEUE:
        partner = _RANDOM_QUEUE.pop(0)
        if partner == cookie:
            continue
        if partner in _CLIENT_ROOM:
            continue
        # Match!
        room_id = create_room(random=True)
        join_room(room_id, cookie)
        join_room(room_id, partner)
        return {"matched": room_id}

    # In Queue
    if cookie not in _RANDOM_QUEUE:
        _RANDOM_QUEUE.append(cookie)
    return {"waiting": True}


def random_status(cookie: str) -> dict:
    """Status fuer Polling: matched/waiting/idle."""
    room_id = _CLIENT_ROOM.get(cookie)
    if room_id and _ROOMS.get(room_id, {}).get("random"):
        return {"matched": room_id}
    if cookie in _RANDOM_QUEUE:
        return {"waiting": True}
    return {"idle": True}


def room_info(room_id: str) -> dict | None:
    """Oeffentliche Info ueber einen Raum."""
    r = _ROOMS.get(room_id)
    if not r:
        return None
    return {
        "id": room_id,
        "clients": len(r["clients"]),
        "messages": len(r["messages"]),
        "random": r.get("random", False),
    }


# Debug/Test
def reset() -> None:
    _ROOMS.clear()
    _CLIENT_ROOM.clear()
    _RANDOM_QUEUE.clear()
