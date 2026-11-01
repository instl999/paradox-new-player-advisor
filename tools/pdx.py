"""A small parser for Paradox script (.txt / .gui / .gfx): enough to check generated files and rule triggers.

parse(text) returns a list of Entry(key, op, value), where value is a str, or a list of Entries for `{ ... }`.
Bare values inside a block (as in `{ a b c }`) come back as Entry(None, None, "a").
"""
import re
from typing import NamedTuple

_TOKEN = re.compile(r'\s+|#[^\n]*|"(?:[^"\\\n]|\\.)*"|[{}]|<=|>=|!=|==|\?=|[=<>]|[^\s{}=<>#"]+')


class Entry(NamedTuple):
    key: object
    op: object
    value: object


class ParseError(Exception):
    pass


def tokens(text):
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ParseError(f"unexpected character {text[pos]!r} at line {text.count(chr(10), 0, pos) + 1}")
        tok, pos = m.group(), m.end()
        if not tok.isspace() and not tok.startswith("#"):
            yield tok


_OPS = {"=", "<", ">", "<=", ">=", "!=", "==", "?="}


def parse(text):
    toks = list(tokens(text))
    entries, i = _block(toks, 0, top=True)
    return entries


def _block(toks, i, top=False):
    out = []
    while i < len(toks):
        tok = toks[i]
        if tok == "}":
            if top:
                raise ParseError("unexpected '}'")
            return out, i + 1
        if tok == "{":
            value, i = _block(toks, i + 1)
            out.append(Entry(None, None, value))
            continue
        if i + 1 < len(toks) and toks[i + 1] in _OPS:
            op = toks[i + 1]
            if i + 2 >= len(toks):
                raise ParseError(f"'{tok} {op}' has no value")
            if toks[i + 2] == "{":
                value, i = _block(toks, i + 3)
            else:
                value, i = unquote(toks[i + 2]), i + 3
            out.append(Entry(unquote(tok), op, value))
        else:
            out.append(Entry(None, None, unquote(tok)))
            i += 1
    if not top:
        raise ParseError("unclosed '{'")
    return out, i


def unquote(tok):
    return tok[1:-1] if len(tok) >= 2 and tok[0] == tok[-1] == '"' else tok


def find(entries, key):
    """All values of `key` directly in `entries`."""
    return [e.value for e in entries if e.key == key]


def first(entries, key, default=None):
    found = find(entries, key)
    return found[0] if found else default


def walk(entries):
    """Every Entry in `entries`, depth first."""
    for e in entries:
        yield e
        if isinstance(e.value, list):
            yield from walk(e.value)
