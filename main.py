# app.py — Streamlit Tender Assistant (rev. Jul‑2025 v10‑final)

import os
from urllib.parse import urlparse
import bs4
import google.generativeai as genai
import requests
import streamlit as st
from PyPDF2 import PdfReader
import base64
import html

# ── API / environment ─────────────────────────────────────────────

SERP_KEY = st.secrets["SERPAPI_API_KEY"]
GEMINI_KEY = st.secrets["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_KEY)
MODEL = genai.GenerativeModel("gemini-2.5-flash")

# ── Session defaults ──────────────────────────────────────────────
if "only_eng" not in st.session_state:
    st.session_state["only_eng"] = False

for k in ("accepted", "rejected"):
    if k not in st.session_state:
        st.session_state[k] = {x: set() for x in ("t", "s", "prev", "lit")}

if "queries" not in st.session_state:
    st.session_state["queries"] = {}
if "start_index" not in st.session_state:
    st.session_state["start_index"] = {x: 0 for x in ("t", "s", "prev", "lit")}

# ── Helpers ───────────────────────────────────────────────────────
TRUSTED_LIT_DOMAINS = [".edu", "springer", "sciencedirect", "arxiv", "researchgate", "acm", "ieee"]

def is_scholar_url(url: str) -> bool:
    try:
        return any(d in urlparse(url).netloc.lower() for d in TRUSTED_LIT_DOMAINS)
    except Exception:
        return False

def serp_links(q: str, n: int = 3, start: int = 0, *, engine: str = "google", lit: bool = False, kind: str | None = None):
    resp = requests.get("https://serpapi.com/search", params={"engine": engine, "q": q, "api_key": SERP_KEY, "num": n, "start": start}, timeout=15).json()
    raw = [x.get("link") or x.get("url") for x in resp.get("organic_results", []) if x.get("link") or x.get("url")]
    links = [u for u in raw if is_scholar_url(u)] if lit else raw[:n]
    if kind:
        links = [u for u in links if u not in st.session_state["rejected"][kind]]
    return links

def is_english(soup: bs4.BeautifulSoup) -> bool:
    lang = soup.html.get("lang", "") if soup.html else ""
    if not lang:
        meta = soup.find("meta", attrs={"http-equiv": "content-language"})
        lang = meta.get("content", "") if meta else ""
    return (not lang) or lang.lower().startswith("en")

def fetch_text(url: str, max_chars: int = 8000) -> str:
    try:
        soup = bs4.BeautifulSoup(requests.get(url, timeout=10).text, "html.parser")
        if st.session_state["only_eng"] and not is_english(soup):
            return ""
        return soup.get_text(" ", strip=True)[:max_chars]
    except Exception:
        return ""

def pdf_to_text(file):
    return "".join(p.extract_text() or "" for p in PdfReader(file).pages[:3])

def gemini(prompt: str):
    return MODEL.generate_content(prompt).text

def build_prompt(role: str, docs: str, product: str) -> str:
    head = {"tender": "You are a public tender expert for Dublin City Council.", "supplier": f"You are a market analyst advising a municipality about {product}."}[role]
    return f"{head}\n\nBelow are documents scraped from the web:\n{docs}\n\nWrite **exactly five** clarification questions the municipality must answer before drafting a tender.\nOutput format strictly:\nQUESTIONS:\n1. ...\n2. ...\n3. ...\n4. ...\n5. ..."

def extract_questions(text: str):
    return [ln.strip() for ln in text.splitlines() if ln.lstrip().startswith(tuple("12345"))]

def add_bg_from_local(image_file):
    with open(image_file, "rb") as image:
        encoded = base64.b64encode(image.read()).decode()
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/jpeg;base64,{encoded}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


# ── UI ────────────────────────────────────────────────────────────
add_bg_from_local("background.jpeg")
st.markdown(
    """
    <h1 style='color:#555555; font-size: 42px; font-weight: 600; margin-bottom: 20px;'>
        Smart Tender Assistant
    </h1>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <div style='font-weight:600; font-size:20px; color:#555555; margin-bottom:2px;'>
        Product / Service name
    </div>
    <div style='margin-top:-8px'>
    """,
    unsafe_allow_html=True
)
product = st.text_input("Product Name", placeholder="electric vehicle charging station", label_visibility="collapsed")
st.markdown("</div>", unsafe_allow_html=True)

results_per_query = st.slider("**Results Per Query**", 1, 10, 3)
col1, col2 = st.columns(2)
with col1:
    chk_tender = st.checkbox("Current Tender links", value=True)
    chk_prev = st.checkbox("Previous Tenders (TED/eTenders)")
with col2:
    chk_supplier = st.checkbox("Supplier Links", value=True)
    chk_lit = st.checkbox("Academic literature (Scholar/arXiv)")

st.session_state["only_eng"] = st.checkbox("English Sources Only", value=st.session_state["only_eng"])

if st.button("🔍 Fetch links") and product:
    st.session_state.update({k: [] for k in ("t_links", "s_links", "prev_links", "lit_links", "t_qs", "s_qs")})
    st.session_state["n_results"] = results_per_query
    with st.spinner("Fetching links…"):
        if chk_tender:
            query = f"{product} procurement tender"
            st.session_state.queries["t"] = {"q": query, "lit": False, "engine": "google"}
            st.session_state.t_links = serp_links(query, results_per_query, kind="t")
            st.session_state.start_index["t"] = results_per_query
        if chk_supplier:
            query = f"{product} supplier Europe price"
            st.session_state.queries["s"] = {"q": query, "lit": False, "engine": "google"}
            st.session_state.s_links = serp_links(query, results_per_query, kind="s")
            st.session_state.start_index["s"] = results_per_query
        if chk_prev:
            query = f"site:ted.europa.eu {product}"
            st.session_state.queries["prev"] = {"q": query, "lit": False, "engine": "google"}
            st.session_state.prev_links = serp_links(query, results_per_query, kind="prev")
            st.session_state.start_index["prev"] = results_per_query
        if chk_lit:
            query = f"{product} tender specification"
            st.session_state.queries["lit"] = {"q": query, "lit": True, "engine": "google"}
            st.session_state.lit_links = serp_links(query, results_per_query * 2, lit=True, kind="lit")
            st.session_state.start_index["lit"] = results_per_query * 2

def link_picker(kind: str, header: str):
    accepted = st.session_state["accepted"][kind]
    rejected = st.session_state["rejected"][kind]
    links = st.session_state.get(f"{kind}_links", [])
    if not links and not accepted:
        return
    st.markdown(f"**{header}**")
    combined = links + [u for u in accepted if u not in links]
    for i, url in enumerate(combined):
        c1, c2, c3 = st.columns([6, 1, 1])
        if url in accepted:
            c1.markdown(f"✅ **Saved** — [{url}]({url})")
        else:
            c1.markdown(f"[{url}]({url})")
        if url not in accepted and c2.button("✓", key=f"save_{kind}_{i}"):
            accepted.add(url)
            st.toast("Saved", icon="✅")
            st.rerun()
        if c3.button("✗", key=f"drop_{kind}_{i}"):
            accepted.discard(url)
            rejected.add(url)
            if url in links:
                links.remove(url)
            st.rerun()
    with st.expander("➕ Add another link"):
        new_url = st.text_input("URL", key=f"add_{kind}")
        if st.button("Add", key=f"btn_add_{kind}") and new_url:
            if new_url not in links and new_url not in rejected:
                links.append(new_url)
            st.rerun()
    if st.button("🔄 More suggestions", key=f"more_{kind}"):
        meta = st.session_state["queries"].get(kind)
        if meta:
            start = st.session_state["start_index"][kind]
            n = st.session_state["n_results"]
            extra = serp_links(meta["q"], n, start=start, engine=meta["engine"], lit=meta["lit"], kind=kind)
            for u in extra:
                if u not in links and u not in accepted:
                    links.append(u)
            st.session_state["start_index"][kind] += n
            st.rerun()
    st.session_state[f"{kind}_links"] = links

if any(st.session_state.get(k) for k in ("t_links", "s_links", "prev_links", "lit_links")):
    link_picker("t", "📁 Current Tenders")
    link_picker("s", "🛒 Suppliers")
    link_picker("prev", "📜 Previous Tenders")
    link_picker("lit", "📚 Academic Literature")

# ── Clarification questions ──────────────────────────────────────

if (
    st.button("➞ Generate Questions")
    and st.session_state.get("t_links")
    and st.session_state.get("s_links")
):
    with st.spinner("Downloading page content…"):
        join_text = lambda L: "\n".join(fetch_text(u) for u in L[: results_per_query * 2])
        t_docs = join_text(st.session_state["t_links"] + st.session_state.get("prev_links", []))
        s_docs = join_text(st.session_state["s_links"])
        l_docs = join_text(st.session_state.get("lit_links", []))
    st.session_state.t_qs = extract_questions(gemini(build_prompt("tender", t_docs + "\n" + l_docs, product)))
    st.session_state.s_qs = extract_questions(gemini(build_prompt("supplier", s_docs + "\n" + l_docs, product)))

# ── Q&A and output ───────────────────────────────────────────────

answers_t, answers_s = [], []
if (qs := st.session_state.get("t_qs")):
    st.subheader("📁 Tender Questions")
    for i, q in enumerate(qs, 1):
        answers_t.append(f"{q}\nA: {st.text_input(q, key=f't_{i}')}\n")
if (qs := st.session_state.get("s_qs")):
    st.subheader("🛒 Supplier Questions")
    for i, q in enumerate(qs, 1):
        answers_s.append(f"{q}\nA: {st.text_input(q, key=f's_{i}')}\n")

if st.session_state.get("t_qs"):
    pdf_files = st.file_uploader("📎 Sample tender PDFs (optional, multiple)", type="pdf", accept_multiple_files=True)
else:
    pdf_files = []

if st.button("📄 Generate Final Requirements & Specifications") and (answers_t or answers_s):
    pdf_text = "".join(pdf_to_text(p) for p in pdf_files) if pdf_files else ""

    final_prompt = f"""
You are a senior tender documentation officer at Dublin City Council.

--- EXCERPTS (first pages only) ---
{pdf_text}

--- TENDER ANSWERS ---
{''.join(answers_t)}

--- SUPPLIER ANSWERS ---
{''.join(answers_s)}

Write a **2,000-word** ‘Requirements & Specifications’ section for a new tender. Follow **this structure**:

1. Introduction & Policy Context  
2. Project Scope & Objectives  
3. Technical Requirements  
4. System Architecture & Data  
5. User Access & Payment  
6. Integration with Council Systems  
7. Service Model & SLAs  
8. Risk Management & Training  
9. Legal / Compliance (GDPR, 2014/24/EU, etc.)  
10. Commercials & Budget  
11. Environmental Commitments  
12. Reporting & Monitoring  

Use tables only when summarizing structured data like site details, budgets, SLAs, or KPIs.  
Avoid forcing tabular format for narrative sections.  
Limit table columns to 4 or fewer where possible.  
If table cell text exceeds width, use superscript¹ and add “Table Notes:” below the table.

Use numbered headings, ≤4-column tables, concrete KPIs, and Word-friendly formatting. Do **NOT** output any questions.
"""

    with st.spinner("Generating draft with Gemini…"):
        final_text = gemini(final_prompt)

    st.success("Draft generated!")
    st.download_button("⬇️ Download (txt)", final_text, file_name="Requirements.txt")

    st.subheader("📄 Draft")
    with st.expander("📄 View Draft"):
        st.text_area("Generated Output", final_text, height=500)

