import streamlit as st
import sqlite3
import pandas as pd
import json
import io
import sys
import random
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


def _cols_match_ci(cols_a, cols_b):
    """SQL identifiers/function names are case-insensitive (SUM(x) and sum(x)
    are the same thing), so column-name grading should be too — only whitespace
    and case are normalized away, the actual expression text still must match."""
    norm = lambda cols: [str(c).strip().lower() for c in cols]
    return norm(cols_a) == norm(cols_b)


def run_user_code(code):
    """Execute Python code with stdout captured and stdin blocked (empty).
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

# ==============================================================================
# DIFFICULTY GUIDANCE FOR AI PROMPTS
# ==============================================================================
# Each level has an "intro" (overall complexity description) and a "topics" list
# (the exact concepts questions can be built around). These are the single
# source of truth for BOTH the AI prompt and the topic-selector dropdown in the
# UI, so the dropdown options always match what the AI is actually told to do.
RANDOM_TOPIC_LABEL = "🎲 Surprise me (random topic)"


def _pick_fresh_random_topic(state_key, level, topics):
    """Random topic pick that avoids repeating the exact same topic this level
    just used, so hitting 'Generate New Problem' on Random doesn't hand back
    the same concept twice in a row. Falls back to the full list if there's
    only one topic to choose from."""
    last_used = st.session_state.get(state_key, {}).get(level)
    candidates = [t for t in topics if t != last_used] or topics
    choice = random.choice(candidates)
    st.session_state.setdefault(state_key, {})[level] = choice
    return choice

SQL_DIFFICULTY_GUIDANCE = {
    "Easy": {
        "intro": (
            "Very simple, single-concept query with only ONE thing to do — no combined "
            "conditions, no joins, no aggregation. Should be solvable with a single "
            "short SELECT. Good example: 'find all employees whose name starts with S'. "
            "Do NOT combine two conditions (e.g. do NOT ask 'find the highest salary "
            "among employees whose name starts with S' — that mixes two ideas and is "
            "too hard for this level)."
        ),
        "topics": [
            "Plain SELECT / SELECT DISTINCT on one table",
            "A single WHERE condition (one comparison operator)",
            "ORDER BY (ascending or descending)",
            "LIMIT / OFFSET (e.g. 'top 5 rows')",
            "Column aliasing with AS",
            "A single AND / OR / NOT condition",
            "IN or BETWEEN",
            "LIKE with a wildcard (%, _)",
            "IS NULL / IS NOT NULL",
        ],
    },
    "Basic": {
        "intro": (
            "Simple query that may combine up to two small conditions (e.g. a WHERE "
            "clause plus a simple aggregate like COUNT/AVG on one table), still clearly "
            "beginner-friendly. No joins yet."
        ),
        "topics": [
            "CREATE TABLE / ALTER TABLE / constraints (PRIMARY KEY, NOT NULL, UNIQUE, DEFAULT, CHECK)",
            "CASE WHEN statements (simple, 2-3 branches)",
            "INSERT INTO / UPDATE / DELETE on a single table",
            "Aggregate functions: COUNT, SUM, AVG, MIN, MAX (single table, no JOIN)",
            "GROUP BY",
            "HAVING vs WHERE (simple case)",
            "String functions: CONCAT, SUBSTRING, TRIM, REPLACE, LENGTH",
            "Date functions: DATEADD/DATE, DATEDIFF, EXTRACT/STRFTIME, current date",
            "Math functions: ROUND, CEIL, FLOOR, ABS",
        ],
    },
    "Intermediate": {
        "intro": (
            "Requires combining multiple conditions, a JOIN across two tables, or "
            "GROUP BY with a HAVING clause."
        ),
        "topics": [
            "INNER JOIN across two tables",
            "LEFT JOIN / RIGHT JOIN (including finding unmatched rows)",
            "FULL OUTER JOIN or CROSS JOIN",
            "SELF JOIN",
            "Multi-table joins (3 tables)",
            "MERGE / UPSERT logic",
            "Scalar or nested subqueries (non-correlated)",
            "EXISTS / NOT EXISTS",
            "UNION / UNION ALL",
            "INTERSECT / EXCEPT (or MINUS)",
            "CREATE VIEW / querying a view (updatable vs non-updatable)",
            "CTEs with a WITH clause (non-recursive)",
            "GROUP BY combined with a HAVING clause filtering on an aggregate",
        ],
    },
    "Advanced": {
        "intro": (
            "Complex, realistic, multi-step query requiring careful reasoning — "
            "multiple joins, subqueries, window functions, or nested aggregations."
        ),
        "topics": [
            "Correlated subqueries",
            "Materialized views (or a scenario that mimics one)",
            "Window functions: ROW_NUMBER, RANK, DENSE_RANK, NTILE with OVER()/PARTITION BY",
            "Aggregate window functions (running totals, moving averages)",
            "Offset functions: LAG, LEAD",
            "Frame clauses: ROWS BETWEEN / RANGE BETWEEN",
            "Recursive CTEs (e.g. org charts, hierarchical/tree data)",
            "Stored procedures or functions, simulated as a single SQLite-compatible query",
            "Triggers (framed as 'write the query that achieves what a trigger would')",
            "Multi-join + subquery + aggregation combined in one business scenario",
        ],
    },
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

PYTHON_DIFFICULTY_GUIDANCE = {
    "Easy": {
        "intro": (
            "Very simple, single-concept task with only ONE thing to do — no combined "
            "conditions and no multi-step logic. Should be solvable in a few lines. "
            "Good examples: 'find words in a list longer than 4 letters', 'write a "
            "function that returns the square and cube of a number'. Do NOT combine "
            "multiple conditions or steps — too hard for this level."
        ),
        "topics": [
            "Variables, basic data types, and type conversion/casting",
            "Arithmetic, comparison, and logical operators",
            "if / elif / else (single condition)",
            "for loop over a range or list (single loop, no nesting)",
            "while loop (simple counter)",
            "break / continue / pass",
            "String indexing and slicing",
            "List creation, indexing, slicing, and basic methods (append, len)",
            "Tuple basics (packing/unpacking)",
        ],
    },
    "Basic": {
        "intro": (
            "Simple task that may combine up to two small steps (e.g. filter a list "
            "AND transform it), still clearly beginner-friendly. One core concept at "
            "a time — e.g. loops, conditionals, basic string/list methods."
        ),
        "topics": [
            "Ternary (conditional) expressions",
            "Nested loops or conditionals (up to two levels)",
            "Sets: uniqueness and set operations (union, intersection, difference)",
            "Dictionaries: creation, methods, iteration",
            "Nested data structures (list of dicts / dict of lists) — simple access",
            "Defining functions: def, parameters, default/keyword args, return values",
            "Lambda functions (basic use)",
            "String formatting: f-strings, .format()",
            "Common string methods: split, join, strip, replace, find",
            "File handling basics: open/read/write with a 'with' statement",
            "JSON basics: json.load / json.dumps",
            "datetime/time basics",
        ],
    },
    "Intermediate": {
        "intro": (
            "Requires chaining a few steps of logic, or applying a single meatier "
            "Python concept — e.g. recursion, dictionaries/sets for counting or "
            "grouping, sorting with a custom key, basic OOP (a class with a couple of "
            "methods), string parsing, or list/dict comprehensions."
        ),
        "topics": [
            "List / dict / set comprehensions, generator expressions",
            "*args and **kwargs",
            "Scope: global / nonlocal",
            "Recursion",
            "Regular expressions (re module) for pattern matching",
            "try/except/else/finally and custom exceptions",
            "OOP basics: classes, __init__, self, instance vs class attributes, single inheritance, @staticmethod/@classmethod/@property",
            "The collections module: Counter, defaultdict, namedtuple, deque",
            "map() / filter() and higher-order functions",
            "Searching (linear/binary) and sorting with a custom key via sorted()",
            "pandas basics: DataFrame/Series creation, filtering, groupby",
            "numpy basics: arrays, indexing, basic vectorized operations",
        ],
    },
    "Advanced": {
        "intro": (
            "A more involved algorithmic or design problem — e.g. a small algorithm "
            "(searching, backtracking, dynamic programming basics), decorators, "
            "generators, working with multiple classes/inheritance, or a multi-step "
            "data-processing pipeline over a SINGLE structure (one list/dict), with "
            "edge cases to handle."
        ),
        "topics": [
            "Multiple/multilevel inheritance and polymorphism",
            "Abstract base classes (abc module)",
            "Magic/dunder methods (__str__, __repr__, __len__, __eq__, etc.)",
            "Composition vs inheritance",
            "heapq (priority queues) and bisect (binary search module)",
            "functools: reduce, partial, lru_cache",
            "Decorators (function or class decorators, functools.wraps)",
            "Generators and iterators (__iter__/__next__, yield)",
            "Sorting algorithms implemented from scratch (bubble/merge/quick)",
            "Recursion and backtracking, or dynamic programming basics",
            "pandas advanced: merging, pivoting, multi-index, apply/lambda chains",
            "numpy advanced: broadcasting, vectorized operations, basic linear algebra",
        ],
    },
}


# ==============================================================================
# UI NAVIGATION
# ==============================================================================
st.title("⚡ Dynamic Code Practice (AI Generated)")

col_track, col_diff, col_topic = st.columns(3)
with col_track:
    track = st.selectbox("Select Track:", ["🗄️ SQL Database Practice", "🐍 Python Practice"])
with col_diff:
    level = st.selectbox("Select Difficulty:", ["Easy", "Basic", "Intermediate", "Advanced"])
with col_topic:
    _guidance = SQL_DIFFICULTY_GUIDANCE if track == "🗄️ SQL Database Practice" else PYTHON_DIFFICULTY_GUIDANCE
    topic_choice = st.selectbox(
        "Focus on a specific concept:",
        [RANDOM_TOPIC_LABEL] + _guidance[level]["topics"],
        help="Leave on 'Surprise me' to let the AI pick a topic within this difficulty level, or lock in a specific concept to drill.",
    )

# ==============================================================================
# SESSION STATS
# ==============================================================================
# Tracks how many problems have been solved this session, and how many of those
# were solved WITHOUT ever opening the hint or solution ("clean solves"). Each
# counter only increments once per problem — a problem is marked solved the
# first time it's answered correctly, so re-submitting a correct query/code
# repeatedly doesn't inflate the count.
for _key in ("stats_sql_solved", "stats_sql_clean", "stats_py_solved", "stats_py_clean"):
    if _key not in st.session_state:
        st.session_state[_key] = 0

stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
with stat_col1:
    st.metric("🗄️ SQL Solved", st.session_state.stats_sql_solved)
with stat_col2:
    st.metric("🗄️ SQL Clean Solves", st.session_state.stats_sql_clean, help="Solved without opening the hint or solution")
with stat_col3:
    st.metric("🐍 Python Solved", st.session_state.stats_py_solved)
with stat_col4:
    st.metric("🐍 Python Clean Solves", st.session_state.stats_py_clean, help="Solved without opening the hint or solution")

st.divider()

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


def _topic_instruction(difficulty, guidance_dict, topic):
    """Builds the topic-selection portion of the prompt. If the user locked in a
    specific concept via the dropdown, force the AI to use exactly that concept
    instead of picking randomly."""
    topics_text = "\n".join(f"- {t}" for t in guidance_dict[difficulty]["topics"])
    if topic and topic != RANDOM_TOPIC_LABEL:
        return (
            f'Build the question specifically around this exact concept: "{topic}". '
            f"Do not substitute a different concept even if it feels easier to write — "
            f"the user deliberately chose to drill this one."
        )
    return "Pick ONE topic at random from this list to build the question around:\n" + topics_text


def generate_sql_problem(difficulty, topic=None):
    prompt = f"""
    Generate a unique, creative, and realistic SQL practice question at {difficulty} level.
    Difficulty guidance: {SQL_DIFFICULTY_GUIDANCE[difficulty]["intro"]}

    {_topic_instruction(difficulty, SQL_DIFFICULTY_GUIDANCE, topic)}

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
    - "concept_name": short name of the SQL concept this question tests (e.g.
      "LIKE operator", "LEFT JOIN", "Window functions: RANK()")
    - "concept_explanation": a clear, tutorial-style explanation (3-5 sentences) of
      that concept — what it does, its general syntax, and 1-2 short generic
      syntax examples (NOT related to this specific question's tables/data, just
      the general pattern, e.g. "WHERE column LIKE 'A%'" for LIKE). This teaches
      the underlying concept independent of the specific question.
    - "solution_walkthrough": a list of 2-5 short strings, each explaining ONE
      clause/part of solution_sql and what it does in THIS specific query (e.g.
      "WHERE name LIKE '%Pro%' — keeps only rows where the name column contains
      the substring 'Pro' anywhere in it"). Walk through the query roughly in the
      order its clauses execute. Keep each entry to one sentence.
    """
    text = _call_groq(prompt)
    return _parse_json_response(text)


def generate_python_problem(difficulty, topic=None):
    prompt = f"""
    Generate a unique Python coding challenge at {difficulty} level.
    Difficulty guidance: {PYTHON_DIFFICULTY_GUIDANCE[difficulty]["intro"]}

    {_topic_instruction(difficulty, PYTHON_DIFFICULTY_GUIDANCE, topic)}

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
    - "concept_name": short name of the Python concept this question tests (e.g.
      "List comprehensions", "*args and **kwargs", "Decorators")
    - "concept_explanation": a clear, tutorial-style explanation (3-5 sentences) of
      that concept — what it does, its general syntax, and 1-2 short generic code
      examples (NOT related to this specific question's data, just the general
      pattern). This teaches the underlying concept independent of the specific
      question.
    - "solution_walkthrough": a list of 2-5 short strings, each explaining ONE
      meaningful step/line of solution_code and what it does in THIS specific
      solution (e.g. "squares = [n**2 for n in nums] — builds a new list holding
      the square of every number in nums"). Walk through the logic roughly in
      execution order. Keep each entry to one sentence.
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
                if topic_choice == RANDOM_TOPIC_LABEL:
                    actual_topic = _pick_fresh_random_topic(
                        "sql_last_topic_by_level", level, SQL_DIFFICULTY_GUIDANCE[level]["topics"]
                    )
                else:
                    actual_topic = topic_choice
                st.session_state.sql_problem = generate_sql_problem(level, actual_topic)
                st.session_state.sql_show_hint = False
                st.session_state.sql_show_solution = False
                st.session_state.sql_attempts = 0
                st.session_state.sql_problem_solved = False
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
        if problem.get("concept_name"):
            st.caption(f"🏷️ Concept: {problem['concept_name']}")
        st.markdown(problem['description'])

        st.markdown("**📊 Sample Tables**")
        for table in problem["tables_to_show"]:
            st.caption(f"Table: `{table}`")
            st.dataframe(pd.read_sql_query(f"SELECT * FROM {table}", conn), hide_index=True, use_container_width=True)

        if problem.get("concept_explanation"):
            with st.expander(f"📚 Learn: {problem.get('concept_name', 'this concept')}"):
                st.markdown(problem["concept_explanation"])

        attempts_so_far = st.session_state.get("sql_attempts", 0)
        hint_col, sol_col = st.columns(2)
        with hint_col:
            if st.button("💡 Hint"):
                st.session_state.sql_show_hint = True
        with sol_col:
            solution_unlocked = attempts_so_far >= 3
            if st.button(
                "📖 Solution" if solution_unlocked else f"📖 Solution ({attempts_so_far}/3 attempts)",
                disabled=not solution_unlocked,
                help=None if solution_unlocked else "Try submitting at least 3 attempts to unlock the solution.",
            ):
                st.session_state.sql_show_solution = True

        if st.session_state.get("sql_show_hint"):
            st.info(f"**Hint:** {problem.get('hint', 'Think about which SQL clause filters or aggregates the rows you need.')}")
        if st.session_state.get("sql_show_solution"):
            st.markdown("**📖 Solution:**")
            st.code(problem["solution_sql"], language="sql")
            if problem.get("solution_walkthrough"):
                st.markdown("**🔎 Step-by-step:**")
                for step in problem["solution_walkthrough"]:
                    st.markdown(f"- {step}")
            st.markdown("**Expected output:**")
            st.dataframe(expected_df, hide_index=True, use_container_width=True)

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

                if user_df.shape == expected_df.shape and _cols_match_ci(user_df.columns, expected_df.columns) and (user_df.values == expected_df.values).all():
                    st.balloons()
                    st.success("🎉 Correct! Your query returned the exact expected dataset.")
                    if not st.session_state.get("sql_problem_solved"):
                        st.session_state.sql_problem_solved = True
                        st.session_state.stats_sql_solved += 1
                        if not st.session_state.get("sql_show_hint") and not st.session_state.get("sql_show_solution"):
                            st.session_state.stats_sql_clean += 1
                elif (
                    user_df.shape == expected_df.shape
                    and not _cols_match_ci(user_df.columns, expected_df.columns)
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
                if topic_choice == RANDOM_TOPIC_LABEL:
                    actual_topic = _pick_fresh_random_topic(
                        "py_last_topic_by_level", level, PYTHON_DIFFICULTY_GUIDANCE[level]["topics"]
                    )
                else:
                    actual_topic = topic_choice
                st.session_state.py_problem = generate_python_problem(level, actual_topic)
                st.session_state.py_show_hint = False
                st.session_state.py_show_solution = False
                st.session_state.py_attempts = 0
                st.session_state.py_problem_solved = False
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
        if problem.get("concept_name"):
            st.caption(f"🏷️ Concept: {problem['concept_name']}")
        st.markdown(problem['description'])

        if problem.get("example"):
            st.caption("💭 Example (for illustration only — uses different data than your actual task):")
            st.code(problem["example"], language="text")

        if problem.get("concept_explanation"):
            with st.expander(f"📚 Learn: {problem.get('concept_name', 'this concept')}"):
                st.markdown(problem["concept_explanation"])

        attempts_so_far = st.session_state.get("py_attempts", 0)
        hint_col, sol_col = st.columns(2)
        with hint_col:
            if st.button("💡 Hint"):
                st.session_state.py_show_hint = True
        with sol_col:
            solution_unlocked = attempts_so_far >= 3
            if st.button(
                "📖 Solution" if solution_unlocked else f"📖 Solution ({attempts_so_far}/3 attempts)",
                disabled=not solution_unlocked,
                help=None if solution_unlocked else "Try submitting at least 3 attempts to unlock the solution.",
            ):
                st.session_state.py_show_solution = True

        if st.session_state.get("py_show_hint"):
            st.info(f"**Hint:** {problem.get('hint', 'Break the problem into small steps and print as you go.')}")
        if st.session_state.get("py_show_solution"):
            st.markdown("**📖 Solution:**")
            st.code(problem["solution_code"], language="python")
            if problem.get("solution_walkthrough"):
                st.markdown("**🔎 Step-by-step:**")
                for step in problem["solution_walkthrough"]:
                    st.markdown(f"- {step}")
            try:
                solution_output = run_user_code(problem["solution_code"])
                st.markdown("**Expected output:**")
                st.code(solution_output if solution_output else "[No Output]")
            except Exception:
                pass  # solution should always run cleanly; silently skip display if not

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
                        if not st.session_state.get("py_problem_solved"):
                            st.session_state.py_problem_solved = True
                            st.session_state.stats_py_solved += 1
                            if not st.session_state.get("py_show_hint") and not st.session_state.get("py_show_solution"):
                                st.session_state.stats_py_clean += 1
                    else:
                        st.error("❌ Output mismatch.")
                        st.write("**Your Output:**")
                        st.code(output if output else "[No Output]")
                        st.write("**Expected Output:**")
                        st.code(expected_output if expected_output else "[No Output]")