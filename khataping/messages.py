"""Reminder wording: prompt building, safety checks, and an offline fallback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote

from . import llm
from .ledger import CustomerDue

LANGUAGES = ("English", "Hindi", "Marathi", "Hinglish")
TONES = ("friendly", "polite", "firm")
BUCKET_TONE = {
    "fresh": "friendly",
    "due": "polite",
    "overdue": "firm",
    "long_overdue": "firm",
    "clear": "friendly",
}

# A reminder must never threaten. If a model slips, we fall back to the template.
FORBIDDEN = (
    "police", "court", "legal", "lawyer", "sue ",
    "\u092a\u0941\u0932\u093f\u0938",  # Hindi: police
    "\u0915\u094b\u0930\u094d\u091f",  # Hindi: court
    "\u0915\u093e\u0928\u0942\u0928",  # Hindi: law
    "\u092a\u094b\u0932\u0940\u0938",  # Marathi: police
)


def format_inr(amount: float) -> str:
    """Indian digit grouping: 1234567 -> '12,34,567'."""
    n = int(round(amount))
    digits = str(abs(n))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return ("-" if n < 0 else "") + digits


_TEMPLATES = {
    "English": {
        "open": "Hello {name}, a gentle reminder from {shop}: Rs {amount} is pending on your khata.",
        "friendly": "Whenever it's convenient, please clear it.",
        "polite": "It has been pending for about {days} days. Please clear it soon.",
        "firm": "It has been pending for {days} days. Please pay this week, or let us know when you can.",
        "close": "Thank you!",
        "upi": "UPI: {upi}.",
    },
    "Hindi": {
        "open": "नमस्ते {name} जी, {shop} की ओर से याद दिलाना था कि आपके खाते में ₹{amount} बाकी है।",
        "friendly": "जब सुविधा हो, कृपया चुका दीजिएगा।",
        "polite": "यह लगभग {days} दिन से बाकी है। कृपया जल्द चुका दें।",
        "firm": "यह {days} दिन से बाकी है। कृपया इस हफ़्ते भुगतान कर दें, या बताएँ कब तक हो पाएगा।",
        "close": "धन्यवाद!",
        "upi": "UPI: {upi}।",
    },
    "Marathi": {
        "open": "नमस्कार {name}, {shop} कडून आठवण — तुमच्या खात्यात ₹{amount} बाकी आहे.",
        "friendly": "सोयीनुसार कृपया भरा.",
        "polite": "ही रक्कम सुमारे {days} दिवसांपासून बाकी आहे. कृपया लवकर भरावी.",
        "firm": "ही रक्कम {days} दिवसांपासून बाकी आहे. कृपया या आठवड्यात भरा, किंवा कधी शक्य आहे ते कळवा.",
        "close": "धन्यवाद!",
        "upi": "UPI: {upi}.",
    },
    "Hinglish": {
        "open": "Namaste {name} ji, {shop} se yaad dilana tha ki aapke khate mein ₹{amount} baaki hai.",
        "friendly": "Jab convenient ho, please clear kar dijiyega.",
        "polite": "Ye lagbhag {days} din se pending hai. Please jaldi clear kar dein.",
        "firm": "Ye {days} din se pending hai. Please is hafte tak payment kar dein, ya bata dein kab tak ho payega.",
        "close": "Thank you!",
        "upi": "UPI: {upi}.",
    },
}


def fallback_message(due: CustomerDue, shop: str, language: str, tone: str,
                     upi: str = "") -> str:
    """Offline template, used when no local model is running or its output is unsafe."""
    t = _TEMPLATES[language]
    parts = [
        t["open"].format(name=due.name, shop=shop, amount=format_inr(due.outstanding)),
        t[tone].format(days=due.days_overdue),
    ]
    if upi:
        parts.append(t["upi"].format(upi=upi))
    parts.append(t["close"])
    return " ".join(parts)


def build_prompt(due: CustomerDue, shop: str, language: str, tone: str,
                 upi: str = "") -> str:
    lines = [
        "You write short WhatsApp payment reminders for a small Indian shop.",
        f"Language: {language}. Tone: {tone}.",
        f"Shop name: {shop}.",
        f"Customer name: {due.name}.",
        f"Amount pending: Rs {format_inr(due.outstanding)} (write exactly this amount).",
        f"Days pending: {due.days_overdue}.",
    ]
    if upi:
        lines.append(f"Shop UPI id: {upi} (include it so the customer can pay).")
    lines += [
        "Rules: under 60 words. Respectful and warm. Never threaten, never shame, "
        "never mention police, court or legal action. At most one emoji. "
        "Do not invent amounts, dates or offers.",
        "Output only the message text, nothing else.",
    ]
    return "\n".join(lines)


def is_safe_output(text: str, due: CustomerDue) -> bool:
    """Guardrail: the model must keep the exact amount and stay non-threatening."""
    cleaned = (text or "").strip()
    if not cleaned or len(cleaned) > 600:
        return False
    low = cleaned.lower()
    if any(word in low for word in FORBIDDEN):
        return False
    formatted = format_inr(due.outstanding)
    return formatted in cleaned or formatted.replace(",", "") in cleaned


@dataclass(frozen=True)
class Message:
    text: str
    source: str  # "gemma" or "template"


def generate_message(
    due: CustomerDue,
    shop: str,
    language: str = "Hinglish",
    tone: Optional[str] = None,
    upi: str = "",
    use_llm: bool = True,
    model: str = llm.DEFAULT_MODEL,
    generator: Optional[Callable[..., str]] = None,
) -> Message:
    tone = tone or BUCKET_TONE.get(due.bucket, "polite")
    if use_llm:
        gen = generator or llm.generate
        try:
            text = gen(build_prompt(due, shop, language, tone, upi), model=model)
            if is_safe_output(text, due):
                return Message(text.strip(), "gemma")
        except llm.LLMUnavailable:
            pass
    return Message(fallback_message(due, shop, language, tone, upi), "template")


def whatsapp_link(phone: str, text: str) -> str:
    """wa.me click-to-chat link. 10-digit Indian numbers get the +91 prefix."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    base = f"https://wa.me/{digits}" if digits else "https://wa.me/"
    return f"{base}?text={quote(text)}"
