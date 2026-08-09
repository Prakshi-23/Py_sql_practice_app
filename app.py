import streamlit as st
import sqlite3
import pandas as pd
import json
import io
import sys
from groq import Groq, RateLimitError
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
# Get a free Groq API key (no credit card) at https://console.groq.com/keys
# then add it to your Streamlit secrets as GROQ_API_KEY.
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

# Initialize the Groq client
client = Groq(api_key=GROQ_API_KEY)

# Groq model to use. llama-3.3-70b-versatile is being retired by Groq (announced
# June 2026, shutting down ~August 2026), so we use their recommended replacement:
# openai/gpt-oss-120b — strong instruction-following, good at clean JSON output,
# and a healthy free-tier daily limit (30 RPM / 1,000 requests per day).
GROQ_MODEL = "openai/gpt-oss-120b"

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
SQL_DIFFICULTY_GUIDANCE = {
    "Easy": (
        "Very simple, single-concept query with only ONE thing to do — no combined "
        "conditions, no joins, no aggregation. Should be solvable with a single "
        "short SELECT. Good example: 'find all employees whose name starts with S'. "
        "Do NOT combine two conditions (e.g. do NOT ask 'find the highest salary "
        "among employees whose name starts with S' — that mixes two ideas and is "
        "too hard for this level)."
    ),
    "Basic": (
        "Simple query that may combine up to two small conditions (e.g. a WHERE "
        "clause plus a simple aggregate like COUNT/AVG on one table), still clearly "
        "beginner-friendly. No joins yet."
    ),
    "Intermediate": (
        "Requires combining multiple conditions, a JOIN across two tables, or "
        "GROUP BY with a HAVING clause."
    ),
    "Advanced": (
        "Complex, realistic, multi-step query requiring careful reasoning — "
        "multiple joins, subqueries, window functions, or nested aggregations."
    ),
}

PYTHON_DIFFICULTY_GUIDANCE = {
    "Easy": (
        "Very simple, single-concept task with only ONE thing to do — no combined "
        "conditions and no multi-step logic. Should be solvable in a few lines. "
        "Good examples: 'find words in a list longer than 4 letters', 'write a "
        "function that returns the square and cube of a number'. Do NOT combine "
        "multiple conditions or steps — too hard for this level."
    ),
    "Basic": (
        "Simple task that may combine up to two small steps (e.g. filter a list "
        "AND transform it), still clearly beginner-friendly. One core concept at "
        "a time — e.g. loops, conditionals, basic string/list methods."
    ),
    "Intermediate": (
        "Requires chaining a few steps of logic, or applying a single meatier "
        "Python concept — e.g. recursion, dictionaries/sets for counting or "
        "grouping, sorting with a custom key, basic OOP (a class with a couple of "
        "methods), string parsing, or list/dict comprehensions."
    ),
    "Advanced": (
        "A more involved algorithmic or design problem — e.g. a small algorithm "
        "(searching, backtracking, dynamic programming basics), decorators, "
        "generators, working with multiple classes/inheritance, or a multi-step "
        "data-processing pipeline over a SINGLE structure (one list/dict), with "
        "edge cases to handle."
    ),
}

# IMPORTANT: keep Python problems distinctly Python-flavored, not SQL-in-disguise.
# Since this app has a separate SQL track, Python questions should NOT simulate
# relational-database logic — no joining two or more separate lists of records by
# a shared id/foreign key and aggregating across them (e.g. "employees" joined
# with "projects"/"orders" tables). That pattern belongs in the SQL track. Python
# questions should instead exercise Python-native concepts: string/list/dict
# manipulation, recursion, comprehensions, sorting, basic OOP, algorithms,
# generators/decorators, working with a SINGLE collection of data (not multiple
# linked collections simulating tables).
PYTHON_DOMAIN_GUIDANCE = (
    "Do NOT write a problem that simulates a relational database (e.g. two or "
    "more lists of dicts linked by an id/foreign key that must be joined and "
    "aggregated together, like employees + projects/orders/departments). That "
    "kind of join-and-aggregate problem belongs to this app's separate SQL track, "
    "not Python — write something using Python-native concepts instead."
)

# ==============================================================================
# AI GENERATION LOGIC
# ==============================================================================
def _call_groq(prompt):
    """Send a prompt to Groq and return the raw text response."""
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a JSON-generating API. Respond with ONLY a single raw "
                    "JSON object. Never wrap it in markdown code fences, never add "
                    "any commentary before or after it."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.9,
    )
    return response.choices[0].message.content


def _fix_double_escaping(obj):
    """Some models double-escape control characters inside JSON string values —
    e.g. the string literally contains a backslash followed by 'n' instead of an
    actual newline. json.loads() can't fix this (it's valid JSON, just poorly
    authored), so we clean it up ourselves after parsing."""
    if isinstance(obj, str):
        return (
            obj.replace("\\n", "\n")
               .replace("\\t", "\t")
               .replace('\\"', '"')
        )
    if isinstance(obj, dict):
        return {k: _fix_double_escaping(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_double_escaping(v) for v in obj]
    return obj


def _parse_json_response(text):
    """Strip any accidental markdown fences and parse the JSON payload."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        cleaned = cleaned.removeprefix("json").strip()
    # If the model added stray text, grab just the outermost {...} block
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
    parsed = json.loads(cleaned)
    return _fix_double_escaping(parsed)


def generate_sql_problem(difficulty):
    prompt = f"""
    Generate a unique, creative, and realistic SQL practice question at {difficulty} level.
    Difficulty guidance: {SQL_DIFFICULTY_GUIDANCE[difficulty]}
    Return ONLY a raw JSON object with NO markdown code block formatting (no ```json wrapper).

    IMPORTANT constraint on "solution_sql": the user's query is graded by comparing
    its output DataFrame to solution_sql's output DataFrame EXACTLY, including
    column names. So:
    - Prefer NOT aliasing result columns unless there's a good reason to (e.g. plain
      `SELECT COUNT(*) FROM ...` rather than `SELECT COUNT(*) AS some_alias FROM ...`).
    - If solution_sql has NO explicit "AS" alias on a column, do NOT mention any
      expected column name in the description at all — do not say things like
      "the result should be named COUNT(*)". An un-aliased column's raw expression
      (e.g. "COUNT(*)") is just SQLite's automatic default, not something the user
      chose or needs to replicate deliberately, so calling it out is confusing noise.
    - ONLY if you deliberately give a column a custom "AS" alias (e.g.
      `AS recent_order_count`, `AS total_sales`) — a real word/name, not the raw
      expression — must the "description" explicitly tell the user that exact
      required output column name, e.g. "Name the result column
      'recent_order_count'." Do not leave the user to guess a custom alias.

    The JSON must contain exact keys:
    - "title": short problem title
    - "description": clear task instructions. Only mention an expected output
      column name if solution_sql uses a deliberate custom "AS" alias — never
      mention a default/un-aliased expression like "COUNT(*)" as if it were a
      required name.
    - "setup_sql": complete SQLite CREATE TABLE and INSERT statements with realistic
      sample data (1 simple table for Easy/Basic, 2-3 tables for Intermediate/Advanced)
    - "tables_to_show": list of table names created
    - "solution_sql": the exact correct SQL query to solve the problem
    - "hint": a short, gentle hint (1-2 sentences) that nudges toward the right SQL
      clause/function to use WITHOUT giving away the full query or the answer
    """
    text = _call_groq(prompt)
    return _parse_json_response(text)


def generate_python_problem(difficulty):
    prompt = f"""
    Generate a unique Python coding challenge at {difficulty} level.
    Difficulty guidance: {PYTHON_DIFFICULTY_GUIDANCE[difficulty]}
    Return ONLY a raw JSON object with NO markdown code block formatting.

    {PYTHON_DOMAIN_GUIDANCE}

    IMPORTANT constraint on "starter_code" AND "solution_code": both will be executed
    automatically with NO real stdin available, so neither must ever call input(),
    sys.stdin.read(), sys.stdin.readline(), or any other function that waits for
    user input — doing so would hang forever. Instead, hardcode the sample data
    directly as Python variables/lists/dicts (e.g. `text = "the quick brown fox"`
    instead of reading it from input). "solution_code" MUST use the exact same
    hardcoded sample data/variable names as "starter_code" — it's the same
    program, just with the logic already filled in correctly.

    The JSON must contain exact keys:
    - "title": short problem title
    - "description": clear task instructions
    - "starter_code": template code for the user, with hardcoded sample data as
      described above and a TODO where the logic goes — no input()/stdin reads
    - "solution_code": a complete, correct, runnable solution to the task using
      the SAME hardcoded sample data as starter_code, ending in print statement(s)
      that produce the final output. This will be executed to determine the
      correct expected output — do not also provide a separate written-out
      expected_output string, since it is derived by running this code.
    - "example": a SHORT worked example (1-2 sentences) that illustrates the general
      idea behind the task using DIFFERENT sample data/numbers than the actual
      question uses. For instance if the task is about filtering a list of words by
      length, the example might use a completely different list and threshold. This
      must NOT reuse the exact data or answer from the question itself — it's just
      there to help the user understand the pattern.
    - "hint": a short, gentle hint (1-2 sentences) suggesting a function/approach to
      use WITHOUT giving away the full solution
    """
    text = _call_groq(prompt)
    return _parse_json_response(text)

# ==============================================================================
# SQL ENGINE
# ==============================================================================
if track == "🗄️ SQL Database Practice":
    if st.button("🔄 Generate New SQL Problem", type="secondary") or "sql_problem" not in st.session_state:
        with st.spinner("Creating custom database and dynamic scenario..."):
            try:
                st.session_state.sql_problem = generate_sql_problem(level)
                st.session_state.sql_show_hint = False
                st.session_state.sql_show_solution = False
                st.session_state.sql_attempts = 0
                st.session_state.sql_problem_id = st.session_state.get("sql_problem_id", 0) + 1
            except RateLimitError:
                st.error("⏳ Groq's free-tier rate limit was hit. Wait a minute and try again.")
                st.stop()

    if "sql_problem" not in st.session_state:
        st.stop()

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

        hint_col, sol_col = st.columns(2)
        with hint_col:
            if st.button("💡 Hint"):
                st.session_state.sql_show_hint = True
        with sol_col:
            if st.session_state.get("sql_attempts", 0) >= 3:
                if st.button("📖 Solution"):
                    st.session_state.sql_show_solution = True

        if st.session_state.get("sql_show_hint"):
            st.info(f"**Hint:** {problem.get('hint', 'Think about which SQL clause filters or aggregates the rows you need.')}")
        if st.session_state.get("sql_show_solution"):
            st.markdown("**📖 Solution:**")
            st.code(problem["solution_sql"], language="sql")

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
            st.session_state.sql_attempts = st.session_state.get("sql_attempts", 0) + 1
            try:
                user_df = pd.read_sql_query(user_query, conn)
                st.write("**Your Query Output:**")
                st.dataframe(user_df, hide_index=True)

                if user_df.equals(expected_df):
                    st.balloons()
                    st.success("🎉 Correct! Your query returned the exact expected dataset.")
                elif (
                    user_df.shape == expected_df.shape
                    and list(user_df.columns) != list(expected_df.columns)
                    and (user_df.values == expected_df.values).all()
                ):
                    # Values match exactly, only the column name(s) differ — this is
                    # a naming/aliasing mismatch, not a logic error. Tell the user
                    # exactly what column name(s) are expected instead of a generic error.
                    expected_cols = ", ".join(f"`{c}`" for c in expected_df.columns)
                    st.warning(
                        f"🟡 Your data/values are correct, but the expected output "
                        f"column name(s) are {expected_cols}. Add an alias to your "
                        f"query, e.g. `AS {expected_df.columns[0]}`, and resubmit."
                    )
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
            try:
                st.session_state.py_problem = generate_python_problem(level)
                st.session_state.py_show_hint = False
                st.session_state.py_show_solution = False
                st.session_state.py_attempts = 0
                st.session_state.py_problem_id = st.session_state.get("py_problem_id", 0) + 1
            except RateLimitError:
                st.error("⏳ Groq's free-tier rate limit was hit. Wait a minute and try again.")
                st.stop()

    if "py_problem" not in st.session_state:
        st.stop()

    problem = st.session_state.py_problem

    left, right = st.columns([1, 1])

    with left:
        st.subheader(f"📌 {problem['title']} ({level})")
        st.markdown(problem['description'])

        if problem.get("example"):
            st.caption("💭 Example (for illustration only — uses different data than your actual task):")
            st.code(problem["example"], language="text")

        hint_col, sol_col = st.columns(2)
        with hint_col:
            if st.button("💡 Hint"):
                st.session_state.py_show_hint = True
        with sol_col:
            if st.session_state.get("py_attempts", 0) >= 3:
                if st.button("📖 Solution"):
                    st.session_state.py_show_solution = True

        if st.session_state.get("py_show_hint"):
            st.info(f"**Hint:** {problem.get('hint', 'Break the problem into small steps and print as you go.')}")
        if st.session_state.get("py_show_solution"):
            st.markdown("**📖 Solution:**")
            st.code(problem["solution_code"], language="python")

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

        def run_user_code(code):
            """Execute user code with stdout captured and stdin blocked (empty).
            If the code tries to read input (input()/sys.stdin.read()), it fails
            immediately with EOFError instead of hanging forever waiting for
            input that will never arrive in this app."""
            buffer = io.StringIO()
            old_stdout, old_stdin = sys.stdout, sys.stdin
            sys.stdout = buffer
            sys.stdin = io.StringIO("")  # empty stdin -> input() raises EOFError immediately
            try:
                exec(code)
                return buffer.getvalue()
            finally:
                sys.stdout, sys.stdin = old_stdout, old_stdin

        run_col, submit_col = st.columns(2)
        with run_col:
            run_clicked = st.button("▶️ Run", use_container_width=True)
        with submit_col:
            submit_clicked = st.button("✅ Submit", type="primary", use_container_width=True)

        if run_clicked:
            try:
                output = run_user_code(user_code)
                st.write("**Output:**")
                st.code(output if output else "[No Output]")
            except EOFError:
                st.error("⚠️ Your code tried to read input, but this app runs code with no live input available. Use the hardcoded sample data in the starter code instead of input()/sys.stdin.")
            except Exception as e:
                st.error(f"Runtime Error: {e}")

        if submit_clicked:
            st.session_state.py_attempts = st.session_state.get("py_attempts", 0) + 1
            try:
                output = run_user_code(user_code)
            except EOFError:
                st.error("⚠️ Your code tried to read input, but this app runs code with no live input available. Use the hardcoded sample data in the starter code instead of input()/sys.stdin.")
                output = None
            except Exception as e:
                st.error(f"Runtime Error: {e}")
                output = None

            if output is not None:
                try:
                    expected_output = run_user_code(problem["solution_code"])
                except Exception as e:
                    # The AI's own reference solution failed to run — that's a
                    # generation issue, not something the user did wrong.
                    st.error(
                        "⚠️ This question's reference solution failed to run "
                        f"({e}). Please generate a new problem — this one has a bug."
                    )
                    expected_output = None

                if expected_output is not None:
                    if output.strip() == expected_output.strip():
                        st.balloons()
                        st.success("🎉 Correct! Output matches expected result.")
                    else:
                        st.error("❌ Output mismatch.")
                        st.write("**Your Output:**")
                        st.code(output if output else "[No Output]")
                        st.write("**Expected Output:**")
                        st.code(expected_output if expected_output else "[No Output]")