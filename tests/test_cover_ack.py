"""Tests für FRAME_COVER_ACK (Stufe 4b)."""

import os
import struct

import pytest
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from erebos_network.tunnel import (
    FRAME_COVER_ACK,
    FRAME_DATA,
    FRAME_COVER,
    _apply_padding,
    _strip_padding,
    _send_cover_ack,
)


class FakeWriter:
    def __init__(self):
        self.buffer = bytearray()

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        pass


def _extract_frames(buffer: bytes) -> list:
    frames = []
    i = 0
    while i + 4 <= len(buffer):
        length = struct.unpack("!I", buffer[i:i+4])[0]
        i += 4
        if i + length > len(buffer):
            break
        frames.append(buffer[i:i+length])
        i += length
    return frames


class TestSendCoverAck:
    @pytest.mark.asyncio
    async def test_send_cover_ack_writes_one_frame(self):
        key = ChaCha20Poly1305.generate_key()
        cipher = ChaCha20Poly1305(key)
        writer = FakeWriter()
        await _send_cover_ack(writer, cipher, size_min=64, size_max=64)
        frames = _extract_frames(bytes(writer.buffer))
        assert len(frames) == 1

    @pytest.mark.asyncio
    async def test_send_cover_ack_payload_starts_with_type(self):
        key = ChaCha20Poly1305.generate_key()
        cipher = ChaCha20Poly1305(key)
        writer = FakeWriter()
        await _send_cover_ack(writer, cipher, size_min=64, size_max=64)
        frames = _extract_frames(bytes(writer.buffer))
        nonce, ct = frames[0][:12], frames[0][12:]
        padded = cipher.decrypt(nonce, ct, None)
        data = _strip_padding(padded)
        assert data[0] == FRAME_COVER_ACK

    @pytest.mark.asyncio
    async def test_send_cover_ack_size_bounds(self):
        key = ChaCha20Poly1305.generate_key()
        cipher = ChaCha20Poly1305(key)
        writer = FakeWriter()
        await _send_cover_ack(writer, cipher, size_min=200, size_max=200)
        frames = _extract_frames(bytes(writer.buffer))
        nonce, ct = frames[0][:12], frames[0][12:]
        padded = cipher.decrypt(nonce, ct, None)
        data = _strip_padding(padded)
        assert len(data) == 201  # 1 Byte Typ + 200 Byte Payload


class TestReceiveFiltering:
    def _make_frame(self, cipher, frame_type: int, payload: bytes) -> bytes:
        typed = bytes([frame_type]) + payload
        padded = _apply_padding(typed)
        nonce = os.urandom(12)
        ct = cipher.encrypt(nonce, padded, None)
        return nonce + ct

    def _make_reader(self, frames):
        buffer = bytearray()
        for f in frames:
            buffer.extend(struct.pack("!I", len(f)) + f)

        class FakeReader:
            def __init__(self, data):
                self.data = data
                self.pos = 0

            async def readexactly(self, n):
                chunk = self.data[self.pos:self.pos+n]
                self.pos += n
                return chunk

        return FakeReader(bytes(buffer))

    @pytest.mark.asyncio
    async def test_receive_filters_cover_ack(self):
        from erebos_network.tunnel import ErebosTunnelClient

        cipher = ChaCha20Poly1305(ChaCha20Poly1305.generate_key())
        ack_frame = self._make_frame(cipher, FRAME_COVER_ACK, b"dummy")
        data_frame = self._make_frame(cipher, FRAME_DATA, b"real-payload")

        reader = self._make_reader([ack_frame, data_frame])
        client = ErebosTunnelClient.__new__(ErebosTunnelClient)
        client.reader = reader
        client.cipher = cipher
        client.writer = None

        result = await client.receive()
        assert result == b"real-payload"

    @pytest.mark.asyncio
    async def test_receive_filters_cover(self):
        from erebos_network.tunnel import ErebosTunnelClient

        cipher = ChaCha20Poly1305(ChaCha20Poly1305.generate_key())
        cover_frame = self._make_frame(cipher, FRAME_COVER, b"x" * 100)
        data_frame = self._make_frame(cipher, FRAME_DATA, b"hello")

        reader = self._make_reader([cover_frame, data_frame])
        client = ErebosTunnelClient.__new__(ErebosTunnelClient)
        client.reader = reader
        client.cipher = cipher
        client.writer = None

        result = await client.receive()
        assert result == b"hello"

    @pytest.mark.asyncio
    async def test_receive_filters_multiple_acks(self):
        from erebos_network.tunnel import ErebosTunnelClient

        cipher = ChaCha20Poly1305(ChaCha20Poly1305.generate_key())
        frames = [
            self._make_frame(cipher, FRAME_COVER_ACK, b"a" * 10),
            self._make_frame(cipher, FRAME_COVER_ACK, b"b" * 20),
            self._make_frame(cipher, FRAME_COVER_ACK, b"c" * 30),
            self._make_frame(cipher, FRAME_DATA, b"final"),
        ]

        reader = self._make_reader(frames)
        client = ErebosTunnelClient.__new__(ErebosTunnelClient)
        client.reader = reader
        client.cipher = cipher
        client.writer = None

        result = await client.receive()
        assert result == b"final"
