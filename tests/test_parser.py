"""Unit tests for parser and renderer."""
import unittest
from src.parser import Parser
from src.renderer import Renderer


class TestParserAndRenderer(unittest.TestCase):
    def setUp(self):
        self.parser = Parser()
        self.renderer = Renderer()

    def test_single_literal(self):
        res = self.parser.parse("42")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.ast.value, "42")
        self.assertEqual(self.renderer.render(res), "42")

    def test_binary_expression(self):
        res = self.parser.parse("10 + 20")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.ast.kind, "BinaryExpr")
        self.assertEqual(self.renderer.render(res), "(10 + 20)")

    def test_empty_input(self):
        res = self.parser.parse("")
        self.assertFalse(res.is_valid)
        self.assertIn("Empty expression", res.errors)


if __name__ == "__main__":
    unittest.main()
