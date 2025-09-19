"""Utilities for decoding and applying Git binary patch hunks."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable, Iterator, List, Sequence
import zlib

from unidiff.patch import PatchedFile

logger = logging.getLogger(__name__)

__all__ = [
    "BinaryPatchError",
    "annotate_binary_patches",
    "apply_binary_patch",
]


class BinaryPatchError(Exception):
    """Raised when a Git binary patch cannot be decoded or applied."""


@dataclass(frozen=True)
class _BinaryHunk:
    method: str
    length: int
    data_lines: tuple[str, ...]

    def decoded_chunks(self) -> bytes:
        compressed = bytearray()
        for raw_line in self.data_lines:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            byte_length = _decode_length_prefix(line[0])
            payload = line[1:]
            if len(payload) % 5:
                raise BinaryPatchError(
                    "Corrupt binary hunk: encoded data length is not a multiple of 5"
                )
            chunk = _decode_base85(payload)
            if len(chunk) < byte_length:
                raise BinaryPatchError(
                    "Corrupt binary hunk: decoded data shorter than expected"
                )
            compressed.extend(chunk[:byte_length])
        try:
            inflated = zlib.decompress(bytes(compressed))
        except zlib.error as exc:  # pragma: no cover - zlib error paths are rare
            raise BinaryPatchError(f"Impossibile decomprimere la patch binaria: {exc}") from exc
        if len(inflated) != self.length:
            raise BinaryPatchError(
                "Binary hunk size mismatch: expected "
                f"{self.length} bytes, decoded {len(inflated)} bytes"
            )
        return inflated


@dataclass
class _GitBinaryPatch:
    hunks: list[_BinaryHunk]

    def apply(self, existing: bytes | None, *, file_label: str) -> bytes:
        if not self.hunks:
            raise BinaryPatchError(
                f"Missing binary data for {file_label}: nessun hunk trovato"
            )
        forward = self.hunks[0]
        decoded = forward.decoded_chunks()
        if forward.method == "literal":
            return decoded
        if forward.method == "delta":
            base = existing or b""
            return _apply_delta(base, decoded, file_label=file_label)
        raise BinaryPatchError(
            f"Unsupported binary patch method '{forward.method}' for {file_label}"
        )


_BASE85_ALPHABET = (
    [ord(c) for c in "0123456789"]
    + [ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    + [ord(c) for c in "abcdefghijklmnopqrstuvwxyz"]
    + [ord(c) for c in "!#$%&()*+-"]
    + [ord(c) for c in ";<=>?@^_`{|}~"]
)

_decode_table = [0] * 256
for index, codepoint in enumerate(_BASE85_ALPHABET):
    _decode_table[codepoint] = index + 1


def _decode_base85(encoded: str) -> bytes:
    output = bytearray()
    for idx in range(0, len(encoded), 5):
        chunk = encoded[idx : idx + 5]
        acc = 0
        for ch in chunk:
            value = _decode_table[ord(ch)]
            if not value:
                raise BinaryPatchError(
                    f"Invalid base85 character '{ch}' in binary patch"
                )
            acc = acc * 85 + (value - 1)
        output.extend(
            ((acc >> 24) & 0xFF, (acc >> 16) & 0xFF, (acc >> 8) & 0xFF, acc & 0xFF)
        )
    return bytes(output)


def _decode_length_prefix(marker: str) -> int:
    if "A" <= marker <= "Z":
        return ord(marker) - ord("A") + 1
    if "a" <= marker <= "z":
        return ord(marker) - ord("a") + 27
    raise BinaryPatchError(f"Invalid binary hunk length marker '{marker}'")


def _read_varint(data: bytes, offset: int, *, file_label: str, what: str) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        if offset >= len(data):
            raise BinaryPatchError(
                f"Binary delta for {file_label} is truncated while reading {what}"
            )
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return value, offset


def _apply_delta(base: bytes, delta: bytes, *, file_label: str) -> bytes:
    offset = 0
    base_size, offset = _read_varint(delta, offset, file_label=file_label, what="base size")
    if len(base) != base_size:
        raise BinaryPatchError(
            f"Binary delta for {file_label} expects base size {base_size}, "
            f"found {len(base)}"
        )
    result_size, offset = _read_varint(
        delta, offset, file_label=file_label, what="result size"
    )
    output = bytearray()
    while offset < len(delta):
        opcode = delta[offset]
        offset += 1
        if opcode & 0x80:
            copy_offset = 0
            shift = 0
            for mask in (0x01, 0x02, 0x04, 0x08):
                if opcode & mask:
                    if offset >= len(delta):
                        raise BinaryPatchError(
                            f"Binary delta for {file_label} ended while reading copy offset"
                        )
                    copy_offset |= delta[offset] << shift
                    offset += 1
                shift += 8
            copy_size = 0
            shift = 0
            for mask in (0x10, 0x20, 0x40):
                if opcode & mask:
                    if offset >= len(delta):
                        raise BinaryPatchError(
                            f"Binary delta for {file_label} ended while reading copy size"
                        )
                    copy_size |= delta[offset] << shift
                    offset += 1
                shift += 8
            if copy_size == 0:
                copy_size = 0x10000
            end = copy_offset + copy_size
            if end > len(base):
                raise BinaryPatchError(
                    f"Binary delta for {file_label} copies beyond base data length"
                )
            output.extend(base[copy_offset:end])
        elif opcode:
            literal_length = opcode
            if offset + literal_length > len(delta):
                raise BinaryPatchError(
                    f"Binary delta for {file_label} ended while copying literal data"
                )
            output.extend(delta[offset : offset + literal_length])
            offset += literal_length
        else:
            raise BinaryPatchError(
                f"Binary delta for {file_label} contains invalid opcode 0"
            )
    if len(output) != result_size:
        raise BinaryPatchError(
            f"Binary delta for {file_label} produced {len(output)} bytes, "
            f"expected {result_size}"
        )
    return bytes(output)


def annotate_binary_patches(
    patch: Sequence[PatchedFile], raw_diff: str | Iterable[str]
) -> None:
    """Attach parsed binary hunk information to ``patch`` in-place."""

    sections = list(_extract_binary_sections(raw_diff))
    if not sections:
        return

    binary_files = [pf for pf in patch if getattr(pf, "is_binary_file", False)]
    if len(sections) != len(binary_files):
        logger.warning(
            "Binary patch count mismatch: parsed %s sections for %s binary files",
            len(sections),
            len(binary_files),
        )
    for pf, hunks in zip(binary_files, sections, strict=False):
        setattr(pf, "_git_binary_patch", _GitBinaryPatch(hunks=list(hunks)))


def _extract_binary_sections(raw_diff: str | Iterable[str]) -> Iterator[Sequence[_BinaryHunk]]:
    if isinstance(raw_diff, str):
        lines = raw_diff.splitlines()
    else:
        lines = [line.rstrip("\n") for line in raw_diff]

    index = 0
    length = len(lines)
    while index < length:
        line = lines[index]
        if line != "GIT binary patch":
            index += 1
            continue
        index += 1
        hunks: List[_BinaryHunk] = []
        while index < length:
            header = lines[index]
            if not header:
                index += 1
                continue
            lowered = header.lower()
            if lowered.startswith("literal ") or lowered.startswith("delta "):
                parts = header.split()
                if len(parts) < 2:
                    raise BinaryPatchError(
                        "Malformed binary hunk header without size: '" + header + "'"
                    )
                method = parts[0].lower()
                try:
                    size = int(parts[1])
                except ValueError as exc:
                    raise BinaryPatchError(
                        "Invalid size in binary hunk header: '" + header + "'"
                    ) from exc
                index += 1
                data_lines: List[str] = []
                while index < length:
                    chunk_line = lines[index]
                    index += 1
                    if chunk_line == "":
                        break
                    data_lines.append(chunk_line)
                hunks.append(
                    _BinaryHunk(method=method, length=size, data_lines=tuple(data_lines))
                )
            else:
                break
        if hunks:
            yield hunks


def apply_binary_patch(pf: PatchedFile, existing: bytes | None) -> bytes:
    """Return the new file bytes resulting from applying ``pf`` to ``existing``."""

    label = (pf.path or pf.target_file or pf.source_file or "<binary file>").strip()
    patch = getattr(pf, "_git_binary_patch", None)
    if not isinstance(patch, _GitBinaryPatch):
        raise BinaryPatchError(
            f"Binary diff data missing for {label}: il blocco binario non è stato trovato"
        )
    return patch.apply(existing, file_label=label or "<binary file>")
