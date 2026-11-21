import pytest


class TestRemoveControlChars:
    @pytest.mark.parametrize("char", [
        "\x00", "\x01", "\x07", "\x08",
        "\x0e", "\x1b", "\x7f",
    ])
    def test_removes_control_chars(self, parser, char):
        assert parser.remove_control_chars(f"a{char}b") == "ab"

    @pytest.mark.parametrize("char", [
        "\u00ad",                        # soft hyphen
        "\u200b", "\u200c", "\u200d",    # zero-width
        "\u200e", "\u200f",              # bidi marks
        "\u202a", "\u202b", "\u202c",
        "\u202d", "\u202e",
        "\u2060",                        # word joiner
        "\u2066", "\u2067", "\u2068", "\u2069",
        "\ufeff",                        # BOM
        "\ufffd",                        # replacement char
    ])
    def test_removes_invisible_unicode(self, parser, char):
        assert parser.remove_control_chars(f"a{char}b") == "ab"

    def test_removes_private_use_range(self, parser):
        assert parser.remove_control_chars("a\ue000\ue001b") == "ab"
        assert parser.remove_control_chars("a\U000e007fb") == "ab"

    @pytest.mark.parametrize("space", [
        "\u00a0",   # NBSP
        "\u1680",
        "\u2000", "\u2001", "\u2002", "\u2003",
        "\u2004", "\u2005", "\u2006", "\u2007",
        "\u2008", "\u2009", "\u200a",
        "\u202f", "\u205f", "\u3000",
    ])
    def test_nonstandard_spaces_to_regular(self, parser, space):
        assert parser.remove_control_chars(f"a{space}b") == "a b"

    def test_keeps_newline_and_tab(self, parser):
        # \n и \t не входят в _CONTROL_RE — остаются до схлопывания в clean_text
        assert parser.remove_control_chars("a\nb\tc") == "a\nb\tc"

    def test_keeps_letters_and_punctuation(self, parser):
        text = "Привет, мир! Hello (test) [1] {2}: 你好 🌍"
        assert parser.remove_control_chars(text) == text

    def test_multiple_chars(self, parser):
        assert parser.remove_control_chars("a\x00\x01b\u200b\u200bc") == "abc"


class TestCleanTextWhitespace:
    def test_collapses_spaces(self, parser):
        assert parser.clean_text("a    b") == "a b"

    def test_strips(self, parser):
        assert parser.clean_text("   hello   ") == "hello"

    def test_newlines_and_tabs_collapse(self, parser):
        assert parser.clean_text("a\t\tb\n\nc\r\n d") == "a b c d"

    def test_mixed_whitespace_and_nbsp(self, parser):
        assert parser.clean_text("  a\u00a0\u00a0b \t\n c  ") == "a b c"

    def test_only_whitespace(self, parser):
        assert parser.clean_text("   \t\n\r\u00a0  ") == ""

    def test_empty_string(self, parser):
        assert parser.clean_text("") == ""

    def test_none(self, parser):
        assert parser.clean_text(None) == ""

    def test_single_space_kept(self, parser):
        assert parser.clean_text("a b") == "a b"

    def test_punctuation_with_spaces(self, parser):
        assert parser.clean_text("Hello ,   world !") == "Hello , world !"

    def test_unicode_preserved(self, parser):
        assert parser.clean_text("Привет 🌍 你好") == "Привет 🌍 你好"

    def test_control_then_collapse(self, parser):
        assert parser.clean_text("a\x00   b\u200b   c") == "a b c"


class TestCleanField:
    def test_normal_value(self, parser):
        assert parser.clean_field("  Hello   World  ") == "Hello World"

    def test_none(self, parser):
        assert parser.clean_field(None) is None

    def test_empty(self, parser):
        assert parser.clean_field("") is None

    def test_only_whitespace(self, parser):
        assert parser.clean_field("   \t\n\u00a0 ") is None

    def test_only_control_chars(self, parser):
        assert parser.clean_field("\x00\u200b\ufeff") is None