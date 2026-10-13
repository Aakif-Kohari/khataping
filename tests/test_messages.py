from datetime import date

import pytest

from khataping import llm
from khataping.ledger import CustomerDue
from khataping.messages import (
    LANGUAGES,
    TONES,
    build_prompt,
    fallback_message,
    format_inr,
    generate_message,
    is_safe_output,
    whatsapp_link,
)

DUE = CustomerDue("Ramesh Patil", "9876543210", 1550.0, date(2026, 8, 15), 59,
                  date(2026, 7, 20), "overdue")


@pytest.mark.parametrize(
    "value, expected",
    [(0, "0"), (999, "999"), (1000, "1,000"), (100000, "1,00,000"),
     (1234567, "12,34,567"), (1550, "1,550")],
)
def test_format_inr_uses_indian_grouping(value, expected):
    assert format_inr(value) == expected


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("tone", TONES)
def test_fallback_always_has_name_amount_and_days(language, tone):
    text = fallback_message(DUE, "Patil Kirana", language, tone, upi="shop@upi")
    assert "Ramesh Patil" in text
    assert "1,550" in text
    assert "shop@upi" in text
    assert "{" not in text  # no unfilled placeholders


def test_prompt_pins_exact_amount_and_forbids_threats():
    prompt = build_prompt(DUE, "Patil Kirana", "Hindi", "firm")
    assert "Rs 1,550" in prompt
    assert "Never threaten" in prompt


def test_safe_output_requires_exact_amount():
    assert is_safe_output("Hi Ramesh, Rs 1,550 is pending.", DUE)
    assert is_safe_output("Hi Ramesh, Rs 1550 is pending.", DUE)
    assert not is_safe_output("Hi Ramesh, Rs 1,850 is pending.", DUE)  # wrong amount
    assert not is_safe_output("", DUE)


def test_safe_output_rejects_threats():
    assert not is_safe_output("Pay Rs 1,550 or we call the police.", DUE)
    assert not is_safe_output("Rs 1,550 due, we will take legal action.", DUE)


def test_uses_model_text_when_it_is_safe():
    fake = lambda prompt, model: "Namaste Ramesh ji, Rs 1,550 baaki hai. Thank you!"
    msg = generate_message(DUE, "Patil Kirana", generator=fake)
    assert msg.source == "gemma" and "1,550" in msg.text


def test_falls_back_when_model_is_offline():
    def offline(prompt, model):
        raise llm.LLMUnavailable("no server")

    msg = generate_message(DUE, "Patil Kirana", generator=offline)
    assert msg.source == "template" and "1,550" in msg.text


def test_falls_back_when_model_changes_the_amount():
    wrong = lambda prompt, model: "Hi Ramesh, Rs 9,999 is pending."
    msg = generate_message(DUE, "Patil Kirana", generator=wrong)
    assert msg.source == "template" and "1,550" in msg.text


def test_tone_defaults_follow_bucket():
    fresh = CustomerDue("A", "", 100.0, date(2026, 10, 10), 3, None, "fresh")
    text = generate_message(fresh, "Shop", "English", use_llm=False).text
    assert "Whenever it's convenient" in text


def test_whatsapp_link_prefixes_india_and_encodes_text():
    link = whatsapp_link("98765 43210", "Hi & bye")
    assert link.startswith("https://wa.me/919876543210?text=")
    assert "%26" in link and " " not in link
