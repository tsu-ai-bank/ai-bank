import pytest


class TestMaskEmail:
    @pytest.mark.parametrize("email", [
        "john@mail.com",
        "john.doe@sub.domain.co.uk",
        "user+tag@example.org",
        "a_b-c.d@x-y.io",
        "UPPER@CASE.COM",
    ])
    def test_plain_email(self, parser, email):
        result = parser.mask_personal_data(f"write to {email} now")
        assert email not in result
        assert "[EMAIL]" in result

    def test_multiple_emails(self, parser):
        result = parser.mask_personal_data("a@b.com and c@d.org")
        assert "a@b.com" not in result
        assert "c@d.org" not in result
        assert result.count("[EMAIL]") == 2

    @pytest.mark.parametrize("obfuscated", [
        "john [at] mail [dot] com",
        "john (at) mail (dot) com",
        "john [собака] mail [точка] com",
        "john (собака) mail (точка) com",
        "john [at] sub [dot] domain [dot] co [dot] uk",
    ])
    def test_obfuscated_email(self, parser, obfuscated):
        result = parser.mask_personal_data(f"contact: {obfuscated}")
        assert "[EMAIL]" in result
        for token in ("[at]", "(at)", "[собака]", "(собака)",
                      "[dot]", "(dot)", "[точка]", "(точка)"):
            assert token not in result.lower()

    def test_obfuscated_case_insensitive(self, parser):
        assert "[EMAIL]" in parser.mask_personal_data("John [AT] Mail [DOT] Com")

    def test_no_email_unchanged(self, parser):
        text = "no emails here"
        assert parser.mask_personal_data(text) == text


class TestMaskPhonePositive:
    @pytest.mark.parametrize("phone", [
        "+7 999 123-45-67",
        "+7 (999) 123-45-67",
        "8 (999) 123-45-67",
        "+1-800-555-0199",
        "8 999 123 45 67",
        "9991234567",                     
        "79991234567",                   
        "89991234567",                   
        "+79991234567",
        "00 7999 1234567",                
        "+7 999 123 45 67 доб. 5",
        "123-45-67",                      
    ])
    def test_phone_masked(self, parser, phone):
        result = parser.mask_personal_data(f"call {phone} today")
        assert phone not in result

    def test_phone_mask_marker(self, parser):
        assert parser.mask_personal_data("tel +7 999 123-45-67") == "tel [PHONE]"

    def test_phone_with_dots_separators(self, parser):
        assert parser.mask_personal_data("+7.999.123.45.67") == "[PHONE]"

    def test_phone_with_nonbreaking_space(self, parser):
        assert (
            parser.mask_personal_data("+7\u00a0999\u00a0123\u00a045\u00a067")
            == "[PHONE]"
        )
    def test_phone_with_unicode_dashes(self, parser):
        assert parser.mask_personal_data("+7 999 123\u201345\u201367") == "[PHONE]"

    def test_multiple_phones(self, parser):
        result = parser.mask_personal_data("+7 999 123-45-67 и 8 800 555-35-35")
        assert "+7 999 123-45-67" not in result
        assert "8 800 555-35-35" not in result
        assert result.count("[PHONE]") == 2


class TestMaskPhoneNegative:
    @pytest.mark.parametrize("value", [
        "2024-01-15 12:30",
        "15.01.2024 12:30",
        "2024.01.15",
        "1999-12-31",
    ])
    def test_dates_not_masked(self, parser, value):
        result = parser.mask_personal_data(f"published {value}")
        assert value in result
        assert "[PHONE]" not in result

    @pytest.mark.parametrize("value", [
        "ИНН 7707083893",
        "ОГРН 1027700132195",
        "ОГРНИП 304500116000157",
        "КПП 773601001",
        "ОКПО 00032537",
        "ОКАТО 45286565000",
        "ОКТМО 45315000",
        "БИК 044525225",
    ])
    def test_ids_not_masked(self, parser, value):
        assert parser.mask_personal_data(value) == value

    @pytest.mark.parametrize("value", [
        "1 250 000 000",
        "12 345 678 900",
        "1 000 000 000",
    ])
    def test_prices_not_masked(self, parser, value):
        result = parser.mask_personal_data(f"цена {value} руб.")
        assert value in result
        assert "[PHONE]" not in result

    @pytest.mark.parametrize("value", ["2024", "42", "12345", "123456"])
    def test_short_numbers_not_masked(self, parser, value):
        result = parser.mask_personal_data(f"number {value}")
        assert value in result

    def test_long_digit_not_phone(self, parser):
        assert parser.mask_personal_data("id 123456789") == "id 123456789"

    def test_very_long_number_not_phone(self, parser):
        value = "1234567890123456"  
        assert parser.mask_personal_data(value) == value

    def test_year_not_masked(self, parser):
        assert parser.mask_personal_data("в 2024 году") == "в 2024 году"

    def test_punctuation_around_phone_kept(self, parser):
        assert (
            parser.mask_personal_data("(тел. +7 999 123-45-67).")
            == "(тел. [PHONE])."
        )

class TestMaskPersonalDataMixed:
    def test_email_and_phone(self, parser):
        result = parser.mask_personal_data("john@mail.com, +7 999 123-45-67")
        assert "john@mail.com" not in result
        assert "+7 999 123-45-67" not in result
        assert "[EMAIL]" in result
        assert "[PHONE]" in result

    def test_idempotent(self, parser):
        once = parser.mask_personal_data("john@mail.com +7 999 123-45-67")
        twice = parser.mask_personal_data(once)
        assert once == twice

    def test_date_between_digits_not_glued(self, parser):
        # дата должна вернуться на место, не склеившись с соседями
        text = "2024-01-15 12:30 встреча +7 999 123-45-67"
        result = parser.mask_personal_data(text)
        assert "2024-01-15 12:30" in result
        assert "[PHONE]" in result

    def test_multiple_dates_restored_in_order(self, parser):
        text = "2024-01-15 и 2023-12-31, тел +7 999 123-45-67"
        result = parser.mask_personal_data(text)
        assert "2024-01-15" in result
        assert "2023-12-31" in result

    def test_null_byte_removed(self, parser):
        assert parser.mask_personal_data("a\x00b") == "ab"

    def test_empty(self, parser):
        assert parser.mask_personal_data("") == ""

    def test_plain_text_unchanged(self, parser):
        text = "Просто текст без ПД, 2024 год, ООО «Ромашка»."
        assert parser.mask_personal_data(text) == text


class TestCleanTextPipeline:

    def test_control_then_mask_then_collapse(self, parser):
        raw = "  John\x00Doe  john@mail.com   +7 999 123-45-67  "
        assert parser.clean_text(raw) == "JohnDoe [EMAIL] [PHONE]"

    def test_unicode_spaces_collapse(self, parser):
        assert parser.clean_text("a\u00a0\u2003b") == "a b"

    def test_obfuscated_email_in_long_text(self, parser):
        raw = "Пишите: ivan [at] mail [dot] ru. Спасибо."
        result = parser.clean_text(raw)
        assert "ivan" not in result
        assert "[EMAIL]" in result

    def test_date_preserved_after_clean(self, parser):
        raw = "Опубликовано 2024-01-15 12:30"
        assert parser.clean_text(raw) == "Опубликовано 2024-01-15 12:30"

    def test_local_phone_masked(self, parser):
        assert parser.clean_text("тел. 123-45-67") == "тел. [PHONE]"

    def test_nbsp_inside_phone(self, parser):
        assert parser.clean_text("+7\u00a0999\u00a0123\u00a045\u00a067") == "[PHONE]"

    def test_phone_spaces_collapse_after_mask(self, parser):
        assert parser.clean_text("тел:  +7  999  123-45-67") == "тел: [PHONE]"