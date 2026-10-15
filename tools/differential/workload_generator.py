#!/usr/bin/env python3
"""M5F v1 neutral deterministic LOBQ1 workload generator — external S1 candidate.

This module never writes files and never computes candidate/reference expected traces.
It is intentionally dependency-free beyond Python's standard library. Deployment,
materialization, corpus sealing and Git changes require separate controls.

Binding precedence: D0 state derivation/draw budget; D1 G4 and base family
rules; D2 corrected G3; D3 precise G1/G2 command choice.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterator

VERSION = "m5f-generator-v1"
PRNG_NAME = "SplitMix64"
MASK64 = (1 << 64) - 1
SEEDS = (
    0x243F6A8885A308D3,
    0x13198A2E03707344,
    0xA4093822299F31D0,
    0x082EFA98EC4E6C89,
)
FAMILY = {
    "G1": (32, 8, 256, 64),
    "G2": (32, 8, 256, 64),
    "G3": (16, 4, 1024, 128),
    "G4": (16, 4, 64, 16),
}
DOMAIN_TAG = b"LOB-M5F-STREAM-V1\x00"


class GenerationError(RuntimeError):
    """Generator failed to satisfy its own frozen workload contract."""


def _require(test: bool, reason: str) -> None:
    if not test:
        raise GenerationError(reason)


def _geometry(family: str, stream_index: int) -> tuple[int, int, int, int]:
    _require(family in FAMILY, "unsupported family")
    _require(type(stream_index) is int, "stream index must be integer")
    count, per_seed, commands, cap = FAMILY[family]
    _require(0 <= stream_index < count, "stream index out of range")
    return count, per_seed, commands, cap


def derive_initial_state(family: str, stream_index: int) -> int:
    """Fixed D0 SHA-256 domain-separated seed derivation."""
    _, per_seed, _, _ = _geometry(family, stream_index)
    preimage = (DOMAIN_TAG + family.encode("ascii") + b"\x00"
                + SEEDS[stream_index // per_seed].to_bytes(8, "big")
                + stream_index.to_bytes(4, "big"))
    return int.from_bytes(sha256(preimage).digest()[:8], "big")


class SplitMix64:
    __slots__ = ("state", "draw_count")

    def __init__(self, seed: int) -> None:
        _require(type(seed) is int and 0 <= seed <= MASK64, "bad rng state")
        self.state = seed
        self.draw_count = 0

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        self.draw_count += 1
        return (z ^ (z >> 31)) & MASK64

    def take_eight(self) -> tuple[int, ...]:
        return tuple(self.next_u64() for _ in range(8))


@dataclass(frozen=True)
class _RestingOrder:
    side: int
    price: int
    quantity: int
    sequence: int


class _SelectionLedger:
    """Private state required for choosing intent; never exported as an oracle.

    This is not used by the G3/G4 fixed-scaffold generators; those are
    independently selected from position and PRNG draws.
    """

    def __init__(self, cap: int) -> None:
        self.orders: dict[int, _RestingOrder] = {}
        self.next_sequence = 1
        self.cap = cap

    def _match(self, oid: int, side: int, price: int, quantity: int, seq: int) -> None:
        remaining = quantity
        while remaining:
            eligible = [
                (i, order) for i, order in self.orders.items()
                if order.side != side
                and (order.price <= price if side == 0 else order.price >= price)
            ]
            if not eligible:
                break
            # Price before time. Sorted deterministic tie order is irrelevant
            # for correct unique sequences, but makes corruption fail-safe.
            maker, order = min(
                eligible,
                key=lambda item: (
                    item[1].price if side == 0 else -item[1].price,
                    item[1].sequence,
                    item[0],
                ),
            )
            traded = min(remaining, order.quantity)
            remaining -= traded
            if traded == order.quantity:
                del self.orders[maker]
            else:
                self.orders[maker] = _RestingOrder(
                    order.side, order.price, order.quantity - traded, order.sequence
                )
        if remaining:
            self.orders[oid] = _RestingOrder(side, price, remaining, seq)

    def apply(self, command: tuple) -> str:
        """Update private planning state; return internal outcome category only."""
        kind = command[0]
        code = "ACCEPT"
        if kind == "N":
            _, oid, side, price, qty = command
            if price <= 0:
                code = "InvalidPrice"
            elif qty <= 0:
                code = "InvalidQuantity"
            elif side not in (0, 1):
                code = "InvalidSide"
            elif oid in self.orders:
                code = "DuplicateOrderId"
            elif self.next_sequence > MASK64:
                code = "SequenceExhausted"
            else:
                seq = self.next_sequence
                self.next_sequence += 1
                self._match(oid, side, price, qty, seq)
        elif kind == "C":
            (_, oid) = command
            if oid not in self.orders:
                code = "UnknownOrderId"
            else:
                del self.orders[oid]
        elif kind == "M":
            _, oid, price, qty = command
            if price <= 0:
                code = "InvalidPrice"
            elif qty <= 0:
                code = "InvalidQuantity"
            elif oid not in self.orders:
                code = "UnknownOrderId"
            else:
                previous = self.orders[oid]
                if price == previous.price and qty == previous.quantity:
                    code = "InvalidModification"
                elif price == previous.price and qty < previous.quantity:
                    self.orders[oid] = _RestingOrder(
                        previous.side, price, qty, previous.sequence
                    )
                else:
                    seq = self.next_sequence
                    _require(seq <= MASK64, "unexpected allocator exhaustion in G1/G2")
                    self.next_sequence += 1
                    del self.orders[oid]
                    self._match(oid, previous.side, price, qty, seq)
        else:
            raise GenerationError("unsupported command kind")
        _require(len(self.orders) <= self.cap, "planning state exceeded cap")
        return code


def _active_id(d2: int, active: dict[int, _RestingOrder]) -> int:
    _require(bool(active), "active ID unavailable")
    ids = sorted(active)
    return ids[d2 % len(ids)]


def _inactive_id(d1: int, active: dict[int, _RestingOrder]) -> int:
    origin = d1 % 128
    for delta in range(128):
        candidate = (origin + delta) % 128
        if candidate not in active:
            return candidate
    raise GenerationError("low-range ID space exhausted")


def _valid_new(draws: tuple[int, ...], ledger: _SelectionLedger) -> tuple:
    _, d1, _, d3, d4, d5, _, d7 = draws
    _require(len(ledger.orders) < ledger.cap, "valid New attempted at cap")
    oid = _inactive_id(d1, ledger.orders)
    side = d3 % 2
    price = 1 + d4 % 1000
    quantity = 1 + d5 % 100
    opposite = [o.price for o in ledger.orders.values() if o.side != side]
    if opposite:
        best = min(opposite) if side == 0 else max(opposite)
        if d7 % 2:
            price = best
        elif side == 0 and best > 1:
            price = min(price, best - 1)
        elif side == 1 and best < 1000:
            price = max(price, best + 1)
        else:
            side = 1 - side
            price = 1 + d4 % 1000
    return ("N", oid, side, price, quantity)


def _valid_modify(draws: tuple[int, ...], ledger: _SelectionLedger) -> tuple:
    oid = _active_id(draws[2], ledger.orders)
    order = ledger.orders[oid]
    variant = draws[6] % 3
    if variant == 0:
        quantity = order.quantity - 1 if order.quantity > 1 else 2
        return ("M", oid, order.price, quantity)
    if variant == 1:
        quantity = order.quantity + 1 if order.quantity < 100 else 99
        return ("M", oid, order.price, quantity)
    price = order.price + 1 if order.price < 1000 else order.price - 1
    return ("M", oid, price, order.quantity)


def _choose_g1(draws: tuple[int, ...], ledger: _SelectionLedger) -> tuple:
    category = draws[0] % 100
    if category < 45:
        if len(ledger.orders) >= 64:
            return ("C", _active_id(draws[2], ledger.orders))
        return _valid_new(draws, ledger)
    if category < 70:
        if not ledger.orders:
            return _valid_new(draws, ledger)
        return ("C", _active_id(draws[2], ledger.orders))
    if not ledger.orders:
        return _valid_new(draws, ledger)
    return _valid_modify(draws, ledger)


def _choose_g2(draws: tuple[int, ...], ledger: _SelectionLedger,
               stream_index: int, slot: int) -> tuple:
    bucket = draws[0] % 100
    active = ledger.orders
    price = 1 + draws[4] % 1000
    qty = 1 + draws[5] % 100

    def valid_new() -> tuple:
        return _valid_new(draws, ledger)

    def selected() -> int:
        return _active_id(draws[2], active)

    def unused() -> int:
        return _inactive_id(draws[1], active)

    def unknown() -> int:
        return 10**12 + 4096 * stream_index + slot

    if bucket < 20:
        if len(active) >= 64:
            return ("C", selected())
        return valid_new()
    if bucket < 30:
        return ("C", selected()) if active else valid_new()
    if bucket < 40:
        return _valid_modify(draws, ledger) if active else valid_new()
    if bucket < 50:
        if not active:
            return valid_new()
        return ("N", selected(), draws[3] % 2, price, qty)
    if bucket < 60:
        return ("N", unused(), 2, price, qty)
    if bucket < 70:
        return ("N", unused(), draws[3] % 2, price, 0)
    if bucket < 80:
        if draws[6] % 2 == 0 or not active:
            return ("N", unused(), draws[3] % 2, 0, qty)
        return ("M", selected(), -1, qty)
    if bucket < 90:
        return ("C", unknown())
    if bucket < 95:
        return ("M", unknown(), price, qty)
    if not active:
        return valid_new()
    oid = selected()
    order = active[oid]
    return ("M", oid, order.price, order.quantity)


def _g3(stream_index: int, rng: SplitMix64) -> Iterator[tuple]:
    for phase in (0, 1):
        for i in range(128):
            rng.take_eight()
            yield ("N", 1000 + i, phase, 300 + i // 8, 20)
        for cycle in range(20):
            first = 1000 + ((34 * cycle) % 128)
            second = first + 1
            price = 900 if phase == 0 else 10
            opp = 1 - phase
            draws = tuple(rng.take_eight() for _ in range(16))
            restored = 350 + draws[14][4] % 200
            motif = (
                ("C", first), ("C", second),
                ("N", 2000, phase, price, 10),
                ("N", 2001, phase, price, 10),
                ("N", 2002, opp, price, 6),
                ("M", 2000, price, 3),
                ("N", 2003, opp, price, 5),
                ("M", 2001, price, 9),
                ("C", 2001),
                ("N", 2000, phase, price, 12),
                ("N", 2001, phase, price, 12),
                ("N", 2004, opp, price, 5),
                ("C", 2000), ("C", 2001),
                ("N", first, phase, restored, 20),
                ("N", second, phase, restored, 20),
            )
            yield from motif
        if phase == 0:
            for i in range(128):
                rng.take_eight()
                yield ("C", 1000 + i)


def _g4(stream_index: int, rng: SplitMix64) -> Iterator[tuple]:
    base = 10000 + 64 * stream_index
    draws = rng.take_eight()
    price = 200 + draws[4] % 600
    yield ("N", base, 0, price, 100)
    for lane in range(1, 8):
        rng.take_eight()
        yield ("N", base + lane, 0, price + lane, 100)
    for lane in range(8):
        oid = base + lane
        unknown = base + 32 + lane
        fresh = base + 16 + lane
        actions = (
            ("M", oid, price + lane, 99),
            ("M", oid, price + lane + 20, 99),
            ("N", fresh, 0, price + lane, 1),
            ("C", unknown),
            ("M", unknown, price + lane, 1),
            ("C", oid),
            ("C", oid),
        )
        for action in actions:
            rng.take_eight()
            yield action


def stream_commands(family: str, stream_index: int) -> tuple[tuple, ...]:
    """Produce exactly one command per frozen position, in memory, never to disk."""
    _, _, count, cap = _geometry(family, stream_index)
    rng = SplitMix64(derive_initial_state(family, stream_index))
    commands: list[tuple] = []
    if family in ("G1", "G2"):
        ledger = _SelectionLedger(cap)
        for slot in range(count):
            draws = rng.take_eight()
            action = (_choose_g1(draws, ledger) if family == "G1" else
                      _choose_g2(draws, ledger, stream_index, slot))
            result = ledger.apply(action)
            if family == "G1":
                _require(result == "ACCEPT", "G1 valid-intent rejection")
            commands.append(action)
    else:
        actions = _g3(stream_index, rng) if family == "G3" else _g4(stream_index, rng)
        commands.extend(actions)
    _require(len(commands) == count, "incorrect stream command count")
    _require(rng.draw_count == 8 * count, "incorrect stream draw budget")
    return tuple(commands)


def serialize_command(command: tuple) -> bytes:
    """Emit exact ASCII decimal LOBQ1 record, with one final LF."""
    _require(bool(command) and command[0] in ("N", "C", "M"), "bad command kind")
    kind = command[0]
    _require(len(command) == {"N": 5, "C": 2, "M": 4}[kind], "bad command arity")
    fields = command[1:]
    _require(all(type(value) is int for value in fields), "non-integer command field")
    oid = fields[0]
    _require(0 <= oid <= MASK64, "order ID representation out of bounds")
    if kind == "N":
        _, side, price, quantity = fields
        _require(0 <= side <= 255, "side representation out of bounds")
        _require(-(1 << 63) <= price < (1 << 63), "price representation out of bounds")
        _require(0 <= quantity <= MASK64, "quantity representation out of bounds")
    elif kind == "M":
        _, price, quantity = fields
        _require(-(1 << 63) <= price < (1 << 63), "price representation out of bounds")
        _require(0 <= quantity <= MASK64, "quantity representation out of bounds")
    record = "|".join(map(str, command)).encode("ascii") + b"\n"
    _require(len(record) - 1 <= 128, "record exceeds transport limit")
    return record


def stream_bytes(family: str, stream_index: int) -> bytes:
    """Return an entire raw LOBQ1 stream in memory; never write it."""
    _geometry(family, stream_index)
    header = b"LOBQ1|18446744073709551608\n" if family == "G4" else b"LOBQ1|1\n"
    return header + b"".join(
        serialize_command(command) for command in stream_commands(family, stream_index)
    )


def stream_path(family: str, stream_index: int) -> str:
    """Return sealer-aligned relative filename, not a write destination action."""
    _geometry(family, stream_index)
    return ("tools/differential/corpus/m5e/generated/" + family.lower() + "/" +
            f"{family}-{stream_index + 1:04d}.lobq1")


__all__ = (
    "VERSION", "PRNG_NAME", "SEEDS", "FAMILY", "SplitMix64",
    "derive_initial_state", "stream_commands", "serialize_command",
    "stream_bytes", "stream_path", "GenerationError",
)
