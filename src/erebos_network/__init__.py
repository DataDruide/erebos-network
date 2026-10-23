"""Erebos Network: Anonymes Netzwerk mit PQC und Hidden Services."""

__version__ = "0.1.0"

from .hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
    verify_descriptor,
    publish_descriptor,
    lookup_descriptor,
)

__all__ = [
    "derive_erebos_address",
    "HiddenServiceDescriptor",
    "IntroPoint",
    "sign_descriptor",
    "verify_descriptor",
    "publish_descriptor",
    "lookup_descriptor",
]
from .hidden_service_client import connect_to_hidden_service
from .hidden_service_server import handle_rendezvous_request
from .intro_point import forward_rendezvous_request, receive_rendezvous_response_from_hs
