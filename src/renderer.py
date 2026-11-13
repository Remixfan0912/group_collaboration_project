"""Expression renderer implementation."""
from src.model import Node, ParseResult


class Renderer:
    def render(self, parse_result: ParseResult) -> str:
        if not parse_result.is_valid or parse_result.ast is None:
            return f"<Error: {', '.join(parse_result.errors)}>"
        return self._render_node(parse_result.ast)

    def _render_node(self, node: Node) -> str:
        if node.kind == "Literal":
            return str(node.value)
        if node.kind == "BinaryExpr":
            left = self._render_node(node.children[0])
            right = self._render_node(node.children[1])
            return f"({left} {node.value} {right})"
        if node.kind == "ExprList":
            return " ".join(self._render_node(c) for c in node.children)
        return str(node.value)
