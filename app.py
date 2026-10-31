import json
import os
import re
import warnings

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq

st.set_page_config(
    page_title="Business Analytics Bot",
    page_icon="📊",
    initial_sidebar_state="collapsed",
)

HISTORY_FILE = "chat_history.json"
MODEL = "openai/gpt-oss-120b"
AVATARS = {"user": "🧑‍💼", "assistant": "📊"}


# ---------- Look and feel ----------
def load_css():
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def hero():
    st.markdown(
        """
        <div class="hero">
            <div class="hero-badge">AI-POWERED ANALYTICS</div>
            <h1>Business Analytics Bot</h1>
            <p>Upload your sales data and ask anything. Every answer is calculated from your actual numbers.</p>
            <p class="hero-typing-line">Try: <span class="fx-typing"></span><span class="fx-cursor">|</span></p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def effects():
    js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "effects.js")
    if os.path.exists(js_path):
        with open(js_path, "r", encoding="utf-8") as f:
            components.html(f"<script>{f.read()}</script>", height=0)


def kpi_cards(data):
    cards = [("Rows", f"{len(data):,}")]
    used = set()
    for key in ["revenue", "sales", "profit", "quantity"]:
        for col in data.columns:
            if col in used:
                continue
            if key in str(col).lower() and pd.api.types.is_numeric_dtype(data[col]):
                cards.append((f"Total {col}", f"{data[col].sum():,.0f}"))
                used.add(col)
                break
    if len(cards) < 4:
        cards.append(("Columns", str(len(data.columns))))
    cards = cards[:4]
    cols = st.columns(len(cards))
    for c, (label, value) in zip(cols, cards):
        c.metric(label, value)


load_css()
hero()
effects()

# ---------- Key ----------
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    api_key = st.sidebar.text_input("Groq API Key", type="password")

# ---------- Upload (main page, so it works on mobile) ----------
file = st.file_uploader("Upload your sales file (CSV or Excel)", type=["csv", "xlsx"])

if not api_key:
    st.info("Please enter your Groq API key in the sidebar (arrow at the top left).")
    st.stop()
if file is None:
    st.info("Upload a CSV or Excel file above to get started.")
    st.stop()

# ---------- Read file ----------
if file.name.endswith(".csv"):
    df = None
    for enc in ["utf-8", "cp1252", "latin-1"]:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        st.error("The file could not be read. Please save it again as CSV UTF-8.")
        st.stop()
else:
    df = pd.read_excel(file)

kpi_cards(df)

with st.expander("Data preview", expanded=False):
    st.dataframe(df.head(10), use_container_width=True)
    st.caption(f"Rows: {len(df)} | Columns: {list(df.columns)}")

client = Groq(api_key=api_key)


# ---------- Chat history (saved in a file) ----------
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(msgs):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(msgs, f, ensure_ascii=False, indent=2)


if "messages" not in st.session_state:
    st.session_state.messages = load_history()

if st.session_state.messages:
    if st.button("Clear chat history", use_container_width=True):
        st.session_state.messages = []
        save_history([])
        st.rerun()

# ---------- AI helpers ----------
columns_info = (
    "Columns and their types:\n" + df.dtypes.to_string()
    + "\n\nFirst 5 rows:\n" + df.head(5).to_string()
)

SAFE_BUILTINS = {
    "len": len, "sum": sum, "min": min, "max": max, "round": round,
    "sorted": sorted, "abs": abs, "str": str, "int": int, "float": float,
    "list": list, "dict": dict, "set": set, "tuple": tuple, "bool": bool,
    "range": range, "enumerate": enumerate, "zip": zip,
}
BANNED = ["import ", "open(", "exec(", "eval(", "__", "os.", "sys.", "subprocess", "input("]


def chat(msgs):
    last_error = None
    for _ in range(3):
        try:
            r = client.chat.completions.create(model=MODEL, messages=msgs)
            content = r.choices[0].message.content
            if content and content.strip():
                return content
            last_error = Exception("The AI returned an empty reply.")
        except Exception as e:
            last_error = e
    raise last_error


def file_overview(data):
    lines = [f"Total rows: {len(data)}", f"Total columns: {len(data.columns)}", ""]
    for col in data.columns:
        s = data[col]
        missing = int(s.isna().sum())
        if pd.api.types.is_numeric_dtype(s):
            lines.append(
                f"{col} (number): min {s.min()}, max {s.max()}, "
                f"total {s.sum()}, average {round(float(s.mean()), 2)}, missing {missing}"
            )
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                dates = pd.to_datetime(s, errors="coerce")
            if dates.notna().mean() > 0.8:
                lines.append(
                    f"{col} (date): from {dates.min().date()} to {dates.max().date()}, missing {missing}"
                )
            else:
                top = s.value_counts().head(5).to_dict()
                lines.append(
                    f"{col} (text): {s.nunique()} unique values, most common: {top}, missing {missing}"
                )
    return "\n".join(lines)


def get_code(question, history, last_code=None, error=None):
    system = (
        "You are a Python pandas expert. A DataFrame called df is already loaded, and pd is available.\n"
        "Write ONLY Python code that computes the answer to the user's question.\n"
        "Rules:\n"
        "- Do not write import statements.\n"
        "- Store the final answer in a variable named 'result' (a number, text, or DataFrame).\n"
        "- Use the column names exactly as shown below.\n"
        "- For text columns (product, country, etc.), match using .str.lower() so spelling case does not matter.\n"
        "- Revenue = price x quantity, if there is no revenue column already.\n"
        "- Profit = revenue minus total cost (unit cost x quantity). If there is no cost column, set result = 'NO_COST_COLUMN'.\n"
        "- If the user asks to explain, describe, summarize or give an overview of the file or data, set result = file_overview(df). (file_overview is already defined.)\n"
                "- If the user just greets, says goodbye, says thanks, or makes small talk (hi, hello, thanks, bye, allah hafiz), set result = 'SMALLTALK'.\n"
        "- If the data needed for the question is not in df at all, set result = 'NOT_IN_DATA'.\n"
        "- The user may write in English or Roman Urdu. Understand both.\n"
        "- Reply with exactly one ```python code block and nothing else.\n\n"
        + columns_info
    )
    msgs = [{"role": "system", "content": system}] + history
    msgs.append({"role": "user", "content": question})
    if error:
        msgs.append({"role": "assistant", "content": last_code or ""})
        msgs.append({
            "role": "user",
            "content": f"That code gave this error: {error}\nFix it and give only the code again.",
        })
    return chat(msgs)


def run_code(code):
    if not code:
        return None, "", "The AI returned no code."
    match = re.search(r"```(?:python)?\s*(.*?)```", code, re.DOTALL)
    if match:
        code = match.group(1)
    code = code.strip()
    for b in BANNED:
        if b in code:
            return None, code, "The code contained something unsafe."
    env = {"__builtins__": SAFE_BUILTINS, "df": df.copy(), "pd": pd, "file_overview": file_overview}
    try:
        exec(code, env)
    except Exception as e:
        return None, code, str(e)
    if "result" not in env:
        return None, code, "No result variable was created."
    return env["result"], code, None


def explain(question, result):
    if hasattr(result, "to_string"):
        result_text = result.to_string()
    else:
        result_text = str(result)
    system = (
        "You are a business analyst. Below is the REAL result computed by pandas from the user's data. "
        "Answer the user's question using only this result. Never invent or change any number.\n"
        "LANGUAGE RULE: reply in English by default. If the user's question is written in "
        "Roman Urdu (Urdu written in English letters), reply in simple Roman Urdu instead.\n"
        "If the result is a file overview (rows, columns and per-column details), explain in simple terms "
        "what this file is about, what each column means, and the key facts such as the number of rows and the date range.\n"
        "If the result is 'SMALLTALK', reply naturally and briefly to what the user actually said: "
        "greet back if they greeted you, say you're welcome if they thanked you, say a warm goodbye "
        "if they are leaving (for example allah hafiz or bye), and answer politely if they asked how you are. "
        "Do not repeat the same greeting every time. Only mention that you can answer questions about "
        "the sales file when it fits naturally.\n"
        "Special results: 'NOT_IN_DATA' means the file does not contain that information. "
        "'NO_COST_COLUMN' means profit cannot be calculated because the file has no cost column. "
        "'COULD_NOT_CALCULATE' means the question could not be calculated and the user should "
        "rephrase it more clearly. Explain these politely in the user's language."
    )
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Question: {question}\n\nResult:\n{result_text[:6000]}"},
    ]
    return chat(msgs)


# ---------- Suggested questions (only when chat is empty) ----------
if not st.session_state.messages:
    st.markdown("##### Try asking")
    for s in ["Explain this file", "What is the total revenue?", "Which product sells the most?"]:
        if st.button(s, use_container_width=True, key=f"sugg_{s}"):
            st.session_state.pending = s

# ---------- Show past chat ----------
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar=AVATARS.get(m["role"])):
        st.write(m["content"])
        if m.get("code"):
            with st.expander("How was this calculated (code)"):
                st.code(m["code"], language="python")

# ---------- New question ----------
typed = st.chat_input("Ask about your sales data...")
question = typed or st.session_state.pop("pending", None)
if question:
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[-6:]
    ]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.write(question)

    used_code = None
    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        with st.spinner("Calculating..."):
            try:
                code, error = None, None
                for attempt in range(2):
                    code = get_code(question, history, code, error)
                    result, code, error = run_code(code)
                    if error is None:
                        break
                if error is not None:
                    text = explain(question, "COULD_NOT_CALCULATE")
                else:
                    if isinstance(result, str) and result.strip() == "NOT_IN_DATA":
                        result = (
                            "FILE OVERVIEW. Use it to answer if relevant; if the question needs "
                            "information that is not covered here, say the file does not contain it.\n\n"
                            + file_overview(df)
                        )
                    text = explain(question, result)
                    if not (isinstance(result, str) and result.strip() == "SMALLTALK"):
                        used_code = code
            except Exception as e:
                text = f"Something went wrong: {e}"
        st.write(text)
        if used_code:
            with st.expander("How was this calculated (code)"):
                st.code(used_code, language="python")

    st.session_state.messages.append(
        {"role": "assistant", "content": text, "code": used_code}
    )
    save_history(st.session_state.messages)