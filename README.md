# KhataPing

**Polite khata reminders for small shops, written by an open-weight model that runs on the shopkeeper's own laptop.**

Built for the [Hacktoberfest Open-Source AI Challenge: Week 2 - Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12).

## The problem

Every kirana, tailor, stationery shop and tuition teacher in India runs a *khata* - a hand-kept ledger of who owes what. Chasing the money is awkward: nobody wants to sound rude to a neighbour they've served for ten years, and the person who forgets to ask loses real money.

KhataPing reads a simple ledger CSV, works out who owes what and for how long, and writes a respectful WhatsApp reminder in the customer's language - Hindi, Marathi, Hinglish or English - with the tone matched to how overdue the balance is.

## Why it can be a small paid tool

- **A real recurring pain:** late khata payments are a cash-flow problem for the shop, every month.
- **Private by design:** customer names, phone numbers and balances stay on the shop's own machine. There is no cloud account and no API key.
- **Near-zero running cost:** the model runs locally, so there is no per-message fee to eat the margin of a tool that would be priced in the range of a small monthly subscription.
- **No lock-in:** swap the model with one setting.

## How it works

```
khata.csv --> ledger.py (plain Python: FIFO settlement, days overdue, stage)
                 |
                 v
          messages.py -- builds a tightly-constrained prompt --> local Gemma (Ollama)
                 |                                                   |
                 |<----------- guardrail: exact amount, no threats --+
                 v
     safe? --yes--> message      no / model offline --> built-in offline template
                 v
          Streamlit UI --> edit --> "Open in WhatsApp" (wa.me link, you press send)
```

Design rules that matter when the subject is money:

1. **The model never does arithmetic.** All balances, ageing and sorting are computed by tested Python in `khataping/ledger.py`. The model only phrases a message around numbers it is given.
2. **The output is checked.** A reply is accepted only if it contains the exact pending amount and nothing threatening (no police, court or legal talk). Otherwise KhataPing silently uses a template.
3. **It works without the model.** If Ollama is not running, the offline templates (all four languages, three tones) are used, so the tool never blocks the shopkeeper.
4. **A human presses send.** KhataPing prepares a WhatsApp link; it never sends anything itself.

## Quick start

```bash
git clone https://github.com/Aakif-Kohari/khataping.git
cd khataping
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Optional but recommended: the local open-weight model
ollama pull gemma3:4b        # any Gemma tag from ollama.com/library/gemma3 works

streamlit run app.py
```

Choose another model with the sidebar field or `KHATAPING_MODEL=<tag>`; point to a different Ollama host with `OLLAMA_URL`.

## Ledger format

| column | required | example |
|--------|----------|---------|
| `customer` | yes | `Ramesh Patil` |
| `date` | yes | `2026-08-15` (also `15-08-2026`, `15/08/2026`) |
| `type` | yes | `credit` / `udhaar` (given on credit) or `payment` / `paid` / `jama` (money received) |
| `amount` | yes | `850` (a rupee sign and commas are fine inside quotes) |
| `phone` | no | `9876543210` (10-digit numbers get +91 automatically) |
| `note` | no | `rice and oil` |

See [`sample_data/khata.csv`](sample_data/khata.csv). All names and numbers in it are invented.

Payments are applied to the **oldest credit first**, so "days overdue" is the age of the oldest credit that is still unpaid. Stages: `fresh` (0-14 days), `due` (15-30), `overdue` (31-60), `long overdue` (61+). Each stage has a default tone (friendly, polite, firm) that you can override per customer.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (41 cases) covers FIFO settlement, overpayment, name grouping, bucket boundaries, malformed-CSV error messages, Indian digit grouping, every language x tone template, the amount/threat guardrail, and the fallback path when the model is offline or changes the number.

## Project layout

```
app.py                  Streamlit UI
khataping/ledger.py     CSV parsing and money maths (no AI)
khataping/messages.py   Prompt, guardrail, offline templates, WhatsApp link
khataping/llm.py        Minimal local Ollama client
sample_data/khata.csv   Invented demo ledger
tests/                  pytest suite
docs/DESIGN.md          Design notes and limitations
```

## Limitations

- WhatsApp sending is manual by design. There is no bot and no bulk-send.
- Hindi and Marathi quality from a small local model varies; always read and edit before sending. The offline templates are deliberately plain and safe.
- It reads a CSV, not a photo of a paper khata (yet).

## License

MIT - see [LICENSE](LICENSE).
