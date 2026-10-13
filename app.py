"""KhataPing - Streamlit UI. Run with: streamlit run app.py"""
from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from khataping import llm
from khataping.ledger import LedgerError, compute_dues, customers_with_dues, parse_ledger
from khataping.messages import (
    BUCKET_TONE,
    LANGUAGES,
    TONES,
    format_inr,
    generate_message,
    whatsapp_link,
)

SAMPLE = Path(__file__).parent / "sample_data" / "khata.csv"

st.set_page_config(page_title="KhataPing", page_icon="📒", layout="wide")
st.title("📒 KhataPing")
st.caption(
    "Polite khata reminders in Hindi, Marathi, Hinglish or English. "
    "Runs on your laptop with an open-weight Gemma model - your customers' "
    "names and balances never leave this machine."
)

with st.sidebar:
    st.header("Your shop")
    shop = st.text_input("Shop name", "Patil Kirana Store")
    upi = st.text_input("UPI ID (optional)", "")
    language = st.selectbox("Message language", LANGUAGES, index=3)
    today = st.date_input("Today", date.today())

    st.header("Local model")
    model = st.text_input("Ollama model tag", llm.DEFAULT_MODEL)
    server_up = llm.ollama_available()
    use_llm = st.toggle("Use Gemma (local)", value=server_up, disabled=not server_up)
    if server_up:
        st.success("Ollama is running locally.")
    else:
        st.info("Ollama not detected - using the built-in offline templates.")

uploaded = st.file_uploader("Upload your khata CSV", type="csv")
st.caption("Columns: customer, date, type (credit/payment), amount - optional: phone, note.")

try:
    if uploaded is not None:
        text = uploaded.getvalue().decode("utf-8-sig")
    else:
        st.info("Showing the bundled sample ledger. Upload your own CSV to replace it.")
        text = SAMPLE.read_text(encoding="utf-8")
    dues = customers_with_dues(compute_dues(parse_ledger(text), today))
except LedgerError as err:
    st.error(str(err))
    st.stop()
except UnicodeDecodeError:
    st.error("Could not read that file. Please save it as a UTF-8 CSV.")
    st.stop()

if not dues:
    st.success("Nobody owes you anything. 🎉")
    st.stop()

total = sum(d.outstanding for d in dues)
c1, c2, c3 = st.columns(3)
c1.metric("Total pending", f"₹{format_inr(total)}")
c2.metric("Customers with dues", len(dues))
c3.metric("Oldest due (days)", dues[0].days_overdue)

st.subheader("Who owes what")
table = pd.DataFrame(
    [
        {
            "Customer": d.name,
            "Pending (₹)": format_inr(d.outstanding),
            "Days": d.days_overdue,
            "Stage": d.bucket.replace("_", " "),
            "Phone": d.phone,
        }
        for d in dues
    ]
)
st.dataframe(table, hide_index=True, width="stretch")

st.subheader("Write a reminder")
names = [d.name for d in dues]
chosen = st.selectbox("Customer", names)
due = next(d for d in dues if d.name == chosen)
tone = st.select_slider("Tone", options=TONES, value=BUCKET_TONE[due.bucket])

if st.button("Write reminder", type="primary"):
    with st.spinner("Writing..."):
        msg = generate_message(due, shop, language, tone, upi, use_llm=use_llm, model=model)
    st.session_state["msg"] = (due.name, msg)

saved = st.session_state.get("msg")
if saved and saved[0] == due.name:
    msg = saved[1]
    label = "Gemma (local)" if msg.source == "gemma" else "offline template"
    st.caption(f"Written by: {label}")
    edited = st.text_area("Edit if you like", msg.text, height=140)
    st.link_button("Open in WhatsApp", whatsapp_link(due.phone, edited))

st.divider()
if st.button("Prepare reminders for everyone"):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["customer", "phone", "pending", "message"])
    progress = st.progress(0.0)
    for i, d in enumerate(dues, start=1):
        m = generate_message(d, shop, language, None, upi, use_llm=use_llm, model=model)
        writer.writerow([d.name, d.phone, format_inr(d.outstanding), m.text])
        progress.progress(i / len(dues))
    st.download_button("Download messages.csv", out.getvalue(), "messages.csv", "text/csv")
