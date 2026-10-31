"""Minimal s-expression parser for KiCad files (.kicad_sch / .kicad_pcb /
.kicad_dru / .kicad_mod / .kicad_sym).

Grammar is a Lisp subset:
    sexp   := atom | '(' sexp* ')'
    atom   := string | symbol | number

Strings are double-quoted with `\"` and `\\` escapes. Symbols are bare
tokens. Numbers are returned as float/int. Lists are returned as Python
lists whose first element is typically a symbol.
"""
from __future__ import annotations
from typing import Any


def parse(text: str) -> list:
    """Parse an s-expression string; return the top-level list."""
    p = _Parser(text)
    p.skip_ws()
    return p.parse_expr()


def parse_all(text: str) -> list:
    """Parse a stream of top-level s-expressions."""
    p = _Parser(text)
    out = []
    p.skip_ws()
    while p.i < len(p.s):
        out.append(p.parse_expr())
        p.skip_ws()
    return out


def find_all(node, head: str):
    """Yield every list whose first element is the symbol `head`, recursively."""
    if isinstance(node, list):
        if node and isinstance(node[0], str) and node[0] == head:
            yield node
        for child in node:
            yield from find_all(child, head)


def first(node, head: str, default: Any = None):
    """Return the first direct child list starting with `head`."""
    if not isinstance(node, list):
        return default
    for child in node:
        if isinstance(child, list) and child and child[0] == head:
            return child
    return default


def value(node, head: str, default: Any = None):
    """For `(head v)`, return v; else default."""
    n = first(node, head)
    if n is None or len(n) < 2:
        return default
    return n[1]


class _Parser:
    def __init__(self, text: str):
        self.s = text
        self.i = 0

    def skip_ws(self):
        while self.i < len(self.s):
            c = self.s[self.i]
            if c.isspace():
                self.i += 1
            elif c == ';':  # line comment (rare but safe)
                while self.i < len(self.s) and self.s[self.i] != '\n':
                    self.i += 1
            else:
                break

    def parse_expr(self):
        self.skip_ws()
        if self.i >= len(self.s):
            raise ValueError("unexpected EOF")
        c = self.s[self.i]
        if c == '(':
            return self._parse_list()
        if c == '"':
            return self._parse_string()
        return self._parse_atom()

    def _parse_list(self):
        assert self.s[self.i] == '('
        self.i += 1
        out = []
        while True:
            self.skip_ws()
            if self.i >= len(self.s):
                raise ValueError("unterminated list")
            if self.s[self.i] == ')':
                self.i += 1
                return out
            out.append(self.parse_expr())

    def _parse_string(self):
        assert self.s[self.i] == '"'
        self.i += 1
        buf = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == '\\':
                self.i += 1
                nxt = self.s[self.i]
                buf.append({'n': '\n', 't': '\t', '"': '"', '\\': '\\'}.get(nxt, nxt))
                self.i += 1
            elif c == '"':
                self.i += 1
                return ''.join(buf)
            else:
                buf.append(c)
                self.i += 1
        raise ValueError("unterminated string")

    def _parse_atom(self):
        start = self.i
        while self.i < len(self.s) and not self.s[self.i].isspace() \
                and self.s[self.i] not in '()"':
            self.i += 1
        token = self.s[start:self.i]
        # Try numeric
        try:
            if '.' in token or 'e' in token or 'E' in token:
                return float(token)
            return int(token)
        except ValueError:
            return token  # bare symbol
