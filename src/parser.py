"""Expression parser implementation."""
import re
from typing import List
from src.model import Token, Node, ParseResult


class Parser:
    def tokenize(self, text: str) -> List[Token]:
        tokens = []
        pos = 0
        token_spec = [
            ("NUMBER", r"\d+"),
            ("OP", r"[+\-*/]"),
            ("LPAREN", r"\("),
            ("RPAREN", r"\)"),
            ("WS", r"\s+"),
        ]
        tok_regex = "|".join(f"(?P<{pair[0]}>{pair[1]})" for pair in token_spec)
        for mo in re.finditer(tok_regex, text):
            kind = mo.lastgroup
            val = mo.group()
            if kind != "WS":
                tokens.append(Token(type=kind, value=val, position=pos))
            pos = mo.end()
        return tokens

    def parse(self, text: str) -> ParseResult:
        tokens = self.tokenize(text)
        if not tokens:
            return ParseResult(ast=None, tokens=[], errors=["Empty expression"])

        # Simple arithmetic parse: only binary expr or single token for baseline
        if len(tokens) == 1:
            return ParseResult(ast=Node(kind="Literal", value=tokens[0].value), tokens=tokens)

        if len(tokens) == 3 and tokens[1].type == "OP":
            left = Node(kind="Literal", value=tokens[0].value)
            right = Node(kind="Literal", value=tokens[2].value)
            root = Node(kind="BinaryExpr", value=tokens[1].value, children=[left, right])
            return ParseResult(ast=root, tokens=tokens)

        # Fallback multi-token
        root = Node(kind="ExprList", children=[Node(kind=t.type, value=t.value) for t in tokens])
        return ParseResult(ast=root, tokens=tokens)
