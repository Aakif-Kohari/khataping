# KhataPing design notes

## Who it is for
A small shop owner who already keeps a khata (paper, Excel, or an app export) and finds reminding customers awkward and easy to postpone.

## Why a local open-weight model
- **Privacy:** a khata is a list of named neighbours and what they owe. Sending that to a third-party API is a poor trade for a tool this small.
- **Cost:** short reminders need a small model; running it locally means no per-message cost.
- **Control:** the model tag is a setting, so the shop is not tied to one vendor's pricing or availability.

## Why the AI is the smallest part
Money maths is deterministic and unit-tested (`ledger.py`). The model is only asked to phrase a message, under a strict prompt, and its output is validated before it is shown (`is_safe_output`). If it fails validation or is unavailable, a template is used instead. The tool is therefore useful even when the model is wrong or absent.

## Guardrail details
- The exact pending amount (Indian grouping or plain digits) must appear in the output.
- Output containing threatening terms (police, court, legal, lawyer, and their Hindi/Marathi equivalents) is rejected.
- Output over 600 characters is rejected.

## Known gaps / next steps
- Read a photo of a paper khata with a local vision model.
- Per-customer language memory.
- Optional reminder schedule (e.g. day 15, day 30) with a "snooze" per customer.
