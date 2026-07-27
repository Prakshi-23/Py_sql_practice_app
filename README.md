# ⚡ AI-Powered Python & SQL Practice App

An AI-powered coding practice platform built with **Streamlit** that generates unique **Python** and **SQL** challenges on demand using the **Groq API**. The application provides an interactive coding environment where users can solve dynamically generated problems, execute their solutions, receive hints, and instantly validate their answers.

## 🚀 Live Demo

### 🌐 https://pysql-practice-app-pkv1.streamlit.app/

> **Note:** The app requires a **Groq API Key** to generate coding challenges.

### Configure the API Key

1. Open your deployed Streamlit app.
2. Click **Manage App**.
3. Go to **Settings → Secrets**.
4. Add the following:

```toml
GROQ_API_KEY = ["YOUR_GROQ_API_KEY"]
```

5. Save the changes.
6. Refresh the application.

The app will now generate Python and SQL practice questions successfully.

You can get a free API key from:
https://console.groq.com/keys

---

# ✨ Features

## 🐍 Python Practice

- AI-generated Python coding challenges
- Four difficulty levels
  - Easy
  - Basic
  - Intermediate
  - Advanced
- Built-in code editor
- Run code instantly
- Output comparison with the expected solution
- Helpful hints
- Automatic solution validation

## 🗄️ SQL Practice

- AI-generated SQL interview questions
- Dynamic SQLite databases created for every question
- Sample tables displayed automatically
- Interactive SQL editor
- Execute SQL queries
- Compare query output with the expected result
- Hints for solving problems

## 🎯 Additional Features

- Dynamic question generation using Groq LLM
- New unique questions every time
- Beautiful Streamlit interface
- Syntax-highlighted Ace editor
- Instant feedback
- Beginner to advanced difficulty levels
- No local database setup required

---

# 🛠️ Tech Stack

- Python
- Streamlit
- Groq API
- SQLite
- Pandas
- Streamlit Ace Editor

---

# 📦 Installation

Clone the repository

```bash
git clone https://github.com/Prakshi-23/Py_sql_practice_app.git
```

Move into the project

```bash
cd Py_sql_practice_app
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create Streamlit secrets

```toml
GROQ_API_KEY = "YOUR_GROQ_API_KEY"
```

Run the application

```bash
streamlit run app.py
```

---

# 📂 Project Highlights

- AI-generated coding problems
- Automatic SQLite database generation
- Real-time Python execution
- SQL query validation
- Interactive code editor
- Difficulty-based question generation
- Instant feedback and hints

---

# 📌 Future Enhancements

- User authentication
- Progress tracking
- Scoreboard
- Saved coding history
- Additional programming languages
- Interview mode
- Timed challenges
- Question bookmarking

---

# 👩‍💻 Author

**Prakshi K**

GitHub:
https://github.com/Prakshi-23

---

⭐ If you like this project, consider giving it a Star!
