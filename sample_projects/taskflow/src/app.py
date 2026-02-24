from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import os

app = Flask(__name__)
DB_PATH = "tasks.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB_PATH):
        conn = get_db()
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT)")
        conn.execute("INSERT INTO tasks (title, status) VALUES ('Initial Task', 'pending')")
        conn.commit()
        conn.close()

@app.route("/")
def index():
    conn = get_db()
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    return render_template("index.html", tasks=tasks)

@app.route("/add", methods=["POST"])
def add_task():
    title = request.form.get("title")
    if title:
        conn = get_db()
        conn.execute("INSERT INTO tasks (title, status) VALUES (?, 'pending')", (title,))
        conn.commit()
        conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    app.run(port=5000)
