"""Minimal blocking SNMP v2c client (standard library only) for Poly endpoints.

Call `fetch()` from an executor; it must not run on the event loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import random
import socket
from typing import Any

# polycom-endpointObjects
ROOT = (1, 3, 6, 1, 4, 1, 13885, 101, 1)
SYS_NAME = (1, 3, 6, 1, 2, 1, 1, 5, 0)

_EXCEPTIONS = (0x80, 0x81, 0x82)  # noSuchObject, noSuchInstance, endOfMibView


class SnmpError(Exception):
    """SNMP request failed or timed out."""


@dataclass
class PolyData:
    """One poll of the device. `oids` is keyed by the suffix under ROOT, e.g. "1.4.0"."""

    sys_name: str | None = None
    oids: dict[str, Any] = field(default_factory=dict)

    def get(self, suffix: str) -> Any:
        return self.oids.get(suffix)

    @property
    def call_indexes(self) -> list[int]:
        """Row indexes present in callActiveCallsTable (keyed off the CallID column)."""
        prefix = "4.1.1.2."
        return sorted(int(k[len(prefix):]) for k in self.oids if k.startswith(prefix))

    def call(self, column: int) -> Any:
        """Value of a callActiveCallsTable column for the first active call, or None."""
        rows = self.call_indexes
        if not rows:
            return None
        value = self.oids.get(f"4.1.1.{column}.{rows[0]}")
        if isinstance(value, str) and value.strip() in ("", "---"):
            return None
        return value


# ---------- BER ----------
def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + _len(len(payload)) + payload


def _int(v: int) -> bytes:
    return _tlv(0x02, v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big", signed=True))


def _oid(oid: tuple[int, ...]) -> bytes:
    out = bytearray()
    for arc in (oid[0] * 40 + oid[1],) + tuple(oid[2:]):
        chunk = [arc & 0x7F]
        arc >>= 7
        while arc:
            chunk.append(0x80 | (arc & 0x7F))
            arc >>= 7
        out.extend(reversed(chunk))
    return _tlv(0x06, bytes(out))


def _read(buf: bytes, pos: int) -> tuple[int, bytes, int]:
    tag = buf[pos]
    ln = buf[pos + 1]
    pos += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[pos:pos + n], "big")
        pos += n
    return tag, buf[pos:pos + ln], pos + ln


def _dec_oid(data: bytes) -> tuple[int, ...]:
    arcs = []
    v = 0
    for byte in data:
        v = (v << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(v)
            v = 0
    if not arcs:
        return ()
    first = arcs[0]
    head = (0, first) if first < 40 else (1, first - 40) if first < 80 else (2, first - 80)
    return head + tuple(arcs[1:])


def _value(tag: int, val: bytes) -> Any:
    if tag == 0x02:
        return int.from_bytes(val, "big", signed=True)
    if tag in (0x41, 0x42, 0x43, 0x46):
        return int.from_bytes(val, "big")
    if tag == 0x04:
        return val.decode("utf-8", errors="replace")
    if tag == 0x06:
        return ".".join(map(str, _dec_oid(val)))
    if tag == 0x40:
        return ".".join(str(b) for b in val)
    return None


class _Client:
    def __init__(self, host: str, port: int, community: str, timeout: float, retries: int) -> None:
        self._addr = (host, port)
        self._community = community.encode()
        self._retries = retries
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(timeout)
        self._req_id = random.randint(1, 0x3FFFFFFF)

    def close(self) -> None:
        self._sock.close()

    def _request(self, pdu_tag: int, a: int, b: int, oid: tuple[int, ...]):
        self._req_id += 1
        vbl = _tlv(0x30, _oid(oid) + _tlv(0x05, b""))
        pdu = _tlv(pdu_tag, _int(self._req_id) + _int(a) + _int(b) + _tlv(0x30, vbl))
        pkt = _tlv(0x30, _int(1) + _tlv(0x04, self._community) + pdu)
        for _ in range(self._retries):
            try:
                self._sock.sendto(pkt, self._addr)
                while True:
                    data, _addr = self._sock.recvfrom(65535)
                    try:
                        parsed = self._parse(data)
                    except (IndexError, ValueError):
                        continue
                    if parsed[0] == self._req_id:
                        return parsed[1], parsed[2]
            except socket.timeout:
                continue
            except OSError as err:
                raise SnmpError(str(err)) from err
        raise SnmpError(f"no SNMP response from {self._addr[0]}:{self._addr[1]}")

    @staticmethod
    def _parse(buf: bytes):
        _, msg, _ = _read(buf, 0)
        _, _, pos = _read(msg, 0)
        _, _, pos = _read(msg, pos)
        _, pdu, _ = _read(msg, pos)
        _, rid, pos = _read(pdu, 0)
        _, es, pos = _read(pdu, pos)
        _, _, pos = _read(pdu, pos)
        _, vbl, _ = _read(pdu, pos)
        out = []
        pos = 0
        while pos < len(vbl):
            _, vb, pos = _read(vbl, pos)
            _, o, p2 = _read(vb, 0)
            vtag, val, _ = _read(vb, p2)
            out.append((_dec_oid(o), vtag, val))
        return int.from_bytes(rid, "big", signed=True), int.from_bytes(es, "big", signed=True), out

    def get(self, oid: tuple[int, ...]) -> Any:
        es, vbs = self._request(0xA0, 0, 0, oid)
        if es or not vbs or vbs[0][1] in _EXCEPTIONS:
            return None
        return _value(vbs[0][1], vbs[0][2])

    def walk(self, root: tuple[int, ...], bulk: int = 25):
        cur = root
        while True:
            es, vbs = self._request(0xA5, 0, bulk, cur)
            if es or not vbs:
                return
            for oid, tag, val in vbs:
                if tag in _EXCEPTIONS or oid[:len(root)] != root or oid <= cur:
                    return
                yield oid, _value(tag, val)
                cur = oid


def fetch(host: str, port: int = 161, community: str = "public",
          timeout: float = 3.0, retries: int = 2) -> PolyData:
    """Walk the Poly endpoint MIB and return the result. Blocking."""
    client = _Client(host, port, community, timeout, retries)
    try:
        data = PolyData(sys_name=client.get(SYS_NAME))
        for oid, value in client.walk(ROOT):
            data.oids[".".join(map(str, oid[len(ROOT):]))] = value
    finally:
        client.close()
    if "1.5.0" not in data.oids:
        raise SnmpError("device did not return the Poly endpoint MIB (no serial number)")
    return data
