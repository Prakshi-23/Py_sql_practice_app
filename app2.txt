import streamlit as st
import sqlite3
import pandas as pd
import json
import io
import sys
from google import genai
from streamlit_ace import st_ace

st.set_page_config(page_title="Dynamic AI Code Practice", page_icon="⚡", layout="wide")

# ==============================================================================
# CUSTOM CODE FONT (Consolas / Courier New / Cascadia Code)
# ==============================================================================
st.markdown(
    """
    <style>
    /* st.code blocks (output panes) */
    code, pre, .stCode, .stCode code, .stCode pre {
        font-family: 'Cascadia Code', Consolas, 'Courier New', monospace !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Shared font stack for the Ace code editor (line numbers + syntax highlighting +
# auto-indent, like HackerRank/LeetCode). Ace uses the first installed font it finds.
EDITOR_FONT = "Cascadia Code, Consolas, 'Courier New', monospace"

# ==============================================================================
# API SETUP
# ==============================================================================
# Paste your free Gemini API key here or use st.secrets / environment variables
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# Initialize the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# ==============================================================================
# UI NAVIGATION
# ==============================================================================
st.title("⚡ Dynamic Code Practice (AI Generated)")

col_track, col_diff = st.columns(2)
with col_track:
    track = st.selectbox("Select Topic:", ["🗄️ SQL Database Practice", "🐍 Python Practice"])
with col_diff:
    level = st.selectbox("Select Difficulty:", ["Easy", "Basic", "Intermediate", "Advanced"])

st.divider()

# ==============================================================================
# DIFFICULTY GUIDANCE FOR AI PROMPTS
# ==============================================================================
DIFFICULTY_GUIDANCE = {
    "Easy": (
        "Very simple, single-concept task with only ONE thing to do — no combined "
        "conditions and no multi-step logic. Should be solvable in a single short "
        "query / a few lines of code. Good examples of the right complexity: "
        "'find all employees whose name starts with S', 'find words in a list that "
        "are longer than 4 letters', 'write a function that returns the square and "
        "cube of a number'. Do NOT combine two conditions (e.g. do NOT ask something "
        "like 'find the highest salary among employees whose name starts with S' — "
        "that mixes two ideas and is too hard for this level)."
    ),
    "Basic": (
        "Simple task that may combine up to two small conditions or steps, still "
        "clearly beginner-friendly."
    ),
    "Intermediate": (
        "Requires combining multiple conditions, joins (for SQL), or a few chained "
        "steps of logic (for Python)."
    ),
    "Advanced": (
        "Complex, realistic, multi-step problem requiring careful reasoning — "
        "possibly multiple joins/subqueries (SQL) or several combined operations "
        "and edge cases (Python)."
    ),
}

# ==============================================================================
# AI GENERATION LOGIC
# ==============================================================================
def generate_sql_problem(difficulty):
    prompt = f"""
    Generate a unique, creative, and realistic SQL practice question at {difficulty} level.
    Difficulty guidance: {DIFFICULTY_GUIDANCE[difficulty]}
    Return ONLY a raw JSON object with NO markdown code block formatting (no ```json wrapper).

    The JSON must contain exact keys:
    - "title": short problem title
    - "description": clear task instructions
    - "setup_sql": complete SQLite CREATE TABLE and INSERT statements with realistic
      sample data (1 simple table for Easy/Basic, 2-3 tables for Intermediate/Advanced)
    - "tables_to_show": list of table names created
    - "solution_sql": the exact correct SQL query to solve the problem
    - "hint": a short, gentle hint (1-2 sentences) that nudges toward the right SQL
      clause/function to use WITHOUT giving away the full query or the answer
    """
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)


def generate_python_problem(difficulty):
    prompt = f"""
    Generate a unique Python coding challenge at {difficulty} level.
    Difficulty guidance: {DIFFICULTY_GUIDANCE[difficulty]}
    Return ONLY a raw JSON object with NO markdown code block formatting.

    The JSON must contain exact keys:
    - "title": short problem title
    - "description": clear task instructions
    - "starter_code": template code for the user
    - "expected_output": the exact stdout text expected when the solution is executed
    - "example": a SHORT worked example (1-2 sentences) that illustrates the general
      idea behind the task using DIFFERENT sample data/numbers than the actual
      question uses. For instance if the task is about filtering a list of words by
      length, the example might use a completely different list and threshold. This
      must NOT reuse the exact data or answer from the question itself — it's just
      there to help the user understand the pattern.
    - "hint": a short, gentle hint (1-2 sentences) suggesting a function/approach to
      use WITHOUT giving away the full solution
    """
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)

# ==============================================================================
# SQL ENGINE
# ==============================================================================
if track == "🗄️ SQL Database Practice":
    if st.button("🔄 Generate New SQL Problem", type="secondary") or "sql_problem" not in st.session_state:
        with st.spinner("Creating custom database and dynamic scenario..."):
            st.session_state.sql_problem = generate_sql_problem(level)
            st.session_state.sql_show_hint = False
            st.session_state.sql_problem_id = st.session_state.get("sql_problem_id", 0) + 1

    problem = st.session_state.sql_problem

    # Initialize SQLite database for this problem
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.executescript(problem["setup_sql"])
    conn.commit()

    # Get Expected Solution Result
    expected_df = pd.read_sql_query(problem["solution_sql"], conn)

    left, right = st.columns([1, 1])

    with left:
        st.subheader(f"📌 {problem['title']} ({level})")
        st.markdown(problem['description'])

        st.markdown("**📊 Sample Tables**")
        for table in problem["tables_to_show"]:
            st.caption(f"Table: `{table}`")
            st.dataframe(pd.read_sql_query(f"SELECT * FROM {table}", conn), hide_index=True, use_container_width=True)

        if st.button("💡 Hint"):
            st.session_state.sql_show_hint = True
        if st.session_state.get("sql_show_hint"):
            st.info(f"**Hint:** {problem.get('hint', 'Think about which SQL clause filters or aggregates the rows you need.')}")

    with right:
        st.markdown("**📝 Your SQL Solution**")
        user_query = st_ace(
            value="SELECT * FROM ...",
            language="sql",
            theme="dracula",
            font_size=15,
            tab_size=4,
            show_gutter=True,       # line numbers
            show_print_margin=False,
            wrap=False,
            auto_update=True,       # live-updates as you type; removes the Apply button
            min_lines=14,
            key=f"sql_editor_{st.session_state.get('sql_problem_id', 0)}",
        )

        run_col, submit_col = st.columns(2)
        with run_col:
            run_clicked = st.button("▶️ Run", use_container_width=True)
        with submit_col:
            submit_clicked = st.button("✅ Submit", type="primary", use_container_width=True)

        if run_clicked:
            try:
                user_df = pd.read_sql_query(user_query, conn)
                st.write("**Query Output:**")
                st.dataframe(user_df, hide_index=True)
            except Exception as e:
                st.error(f"SQL Error: {e}")

        if submit_clicked:
            try:
                user_df = pd.read_sql_query(user_query, conn)
                st.write("**Your Query Output:**")
                st.dataframe(user_df, hide_index=True)

                if user_df.equals(expected_df):
                    st.balloons()
                    st.success("🎉 Correct! Your query returned the exact expected dataset.")
                else:
                    st.error("❌ Output mismatch. Try revising your query.")
            except Exception as e:
                st.error(f"SQL Error: {e}")

# ==============================================================================
# PYTHON ENGINE
# ==============================================================================
else:
    if st.button("🔄 Generate New Python Problem", type="secondary") or "py_problem" not in st.session_state:
        with st.spinner("Building fresh Python challenge..."):
            st.session_state.py_problem = generate_python_problem(level)
            st.session_state.py_show_hint = False
            st.session_state.py_problem_id = st.session_state.get("py_problem_id", 0) + 1

    problem = st.session_state.py_problem

    left, right = st.columns([1, 1])

    with left:
        st.subheader(f"📌 {problem['title']} ({level})")
        st.markdown(problem['description'])

        if problem.get("example"):
            st.caption("💭 Example (for illustration only — uses different data than your actual task):")
            st.code(problem["example"], language="text")

        if st.button("💡 Hint"):
            st.session_state.py_show_hint = True
        if st.session_state.get("py_show_hint"):
            st.info(f"**Hint:** {problem.get('hint', 'Break the problem into small steps and print as you go.')}")

    with right:
        st.markdown("**Your Python Code:**")
        user_code = st_ace(
            value=problem["starter_code"],
            language="python",
            theme="dracula",
            font_size=15,
            tab_size=4,
            show_gutter=True,       # line numbers
            show_print_margin=False,
            wrap=False,
            auto_update=True,       # live-updates as you type; removes the Apply button
            min_lines=14,
            key=f"py_editor_{st.session_state.get('py_problem_id', 0)}",
        )

        run_col, submit_col = st.columns(2)
        with run_col:
            run_clicked = st.button("▶️ Run", use_container_width=True)
        with submit_col:
            submit_clicked = st.button("✅ Submit", type="primary", use_container_width=True)

        if run_clicked:
            buffer = io.StringIO()
            sys.stdout = buffer
            try:
                exec(user_code)
                output = buffer.getvalue()
                st.write("**Output:**")
                st.code(output if output else "[No Output]")
            except Exception as e:
                st.error(f"Runtime Error: {e}")
            finally:
                sys.stdout = sys.__stdout__

        if submit_clicked:
            buffer = io.StringIO()
            sys.stdout = buffer
            try:
                exec(user_code)
                output = buffer.getvalue()

                if output == problem["expected_output"]:
                    st.balloons()
                    st.success("🎉 Correct! Output matches expected result.")
                else:
                    st.error("❌ Output mismatch.")
                    st.write("**Your Output:**")
                    st.code(output if output else "[No Output]")
                    st.write("**Expected Output:**")
                    st.code(problem["expected_output"])
            except Exception as e:
                st.error(f"Runtime Error: {e}")
            finally:
                sys.stdout = sys.__stdout__