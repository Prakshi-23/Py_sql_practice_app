import streamlit as st
import sqlite3
import pandas as pd
import json
import io
import sys
from google import genai

st.set_page_config(page_title="Dynamic AI Code Practice", page_icon="⚡", layout="wide")

# ==============================================================================
# API SETUP
# ==============================================================================
# Paste your free Gemini API key here or use st.secrets / environment variables
# Replace your key definition with this line:
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# Initialize the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# @st.cache_resource
# def get_client():
#     return genai.Client(api_key=GEMINI_API_KEY)

# ==============================================================================
# UI NAVIGATION
# ==============================================================================
st.title("⚡ Dynamic Code Practice (AI Generated)")

col_track, col_diff = st.columns(2)
with col_track:
    track = st.selectbox("Select Topic:", ["🗄️ SQL Database Practice", "🐍 Python Practice"])
with col_diff:
    level = st.selectbox("Select Difficulty:", ["Basic", "Intermediate", "Advanced"])

st.divider()

# ==============================================================================
# AI GENERATION LOGIC
# ==============================================================================
def generate_sql_problem(difficulty):
    client = get_client()
    prompt = f"""
    Generate a unique, creative, and realistic SQL practice question at {difficulty} level.
    Return ONLY a raw JSON object with NO markdown code block formatting (no ```json wrapper).
    
    The JSON must contain exact keys:
    - "title": short problem title
    - "description": clear task instructions
    - "setup_sql": complete SQLite CREATE TABLE and INSERT statements with realistic sample data (2-3 tables for intermediate/advanced)
    - "tables_to_show": list of table names created
    - "solution_sql": the exact correct SQL query to solve the problem
    """
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    # Clean output if necessary
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)

def generate_python_problem(difficulty):
    client = get_client()
    prompt = f"""
    Generate a unique Python coding challenge at {difficulty} level.
    Return ONLY a raw JSON object with NO markdown code block formatting.
    
    The JSON must contain exact keys:
    - "title": short problem title
    - "description": clear task instructions
    - "starter_code": template code for the user
    - "expected_output": the exact stdout text expected when the solution is executed
    """
    response = client.models.generate_content(
        model='gemini-2.5-flash',
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

    problem = st.session_state.sql_problem

    # Initialize SQLite database for this problem
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.executescript(problem["setup_sql"])
    conn.commit()

    # Get Expected Solution Result
    expected_df = pd.read_sql_query(problem["solution_sql"], conn)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader(f"📌 {problem['title']} ({level})")
        st.markdown(problem['description'])

    with col2:
        st.subheader("📊 Generated Sample Tables")
        for table in problem["tables_to_show"]:
            st.caption(f"Table: `{table}`")
            st.dataframe(pd.read_sql_query(f"SELECT * FROM {table}", conn), hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("📝 Your SQL Solution")
    user_query = st.text_area("Write SQL Query:", value="SELECT * FROM ...", height=140)

    if st.button("Submit Query", type="primary"):
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

    problem = st.session_state.py_problem

    st.subheader(f"📌 {problem['title']} ({level})")
    st.markdown(problem['description'])

    st.divider()
    user_code = st.text_area("Your Python Code:", value=problem["starter_code"], height=180)

    if st.button("Run & Submit", type="primary"):
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