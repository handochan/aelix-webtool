"""Streaming gzip/deflate with a decoder-side output bound."""

from __future__ import annotations

import zlib

from .errors import WebToolError


class BodyDecoder:
    def __init__(self, encoding: str, limit: int) -> None:
        self.encoding = encoding.strip().lower()
        if self.encoding not in {"", "identity", "gzip", "deflate"}:
            raise WebToolError(
                "unsupported_encoding",
                "Supported response encodings are identity, gzip and deflate.",
            )
        self.limit = limit
        self.produced = 0
        self.pending = b""
        self.decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if self.encoding == "gzip" else None

    def feed(self, data: bytes) -> bytes:
        if self.encoding in {"", "identity"}:
            output = data
        else:
            if self.decoder is None:
                self.pending += data
                if len(self.pending) < 2:
                    return b""
                first, second = self.pending[:2]
                wrapped = first & 15 == 8 and (first * 256 + second) % 31 == 0
                self.decoder = zlib.decompressobj(zlib.MAX_WBITS if wrapped else -zlib.MAX_WBITS)
                data, self.pending = self.pending, b""
            try:
                output = self.decoder.decompress(data, self.limit - self.produced + 1)
            except zlib.error:
                raise WebToolError(
                    "invalid_response", "The server returned malformed compressed content."
                ) from None
            if self.decoder.unused_data:
                raise WebToolError(
                    "invalid_response",
                    "Trailing or concatenated compressed streams are unsupported.",
                )
        self.produced += len(output)
        if self.produced > self.limit:
            raise WebToolError(
                "response_too_large", f"Decoded response exceeds the {self.limit}-byte limit."
            )
        return output

    def finish(self) -> None:
        if self.encoding not in {"", "identity"} and (self.decoder is None or not self.decoder.eof):
            raise WebToolError(
                "invalid_response", "The server returned truncated compressed content."
            )
