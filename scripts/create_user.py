import argparse
import getpass
import os
import sys

import bcrypt
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

parser = argparse.ArgumentParser(description="Create a Triage Copilot user account")
parser.add_argument("username")
parser.add_argument("--role", choices=["staff", "admin"], default="staff")
args = parser.parse_args()

password = getpass.getpass("Password: ")
if len(password) < 10:
    sys.exit("Password must be at least 10 characters.")
if len(password.encode()) > 72:
    sys.exit("Password must be 72 bytes or fewer (bcrypt limit).")
if password != getpass.getpass("Confirm password: "):
    sys.exit("Passwords did not match.")

engine = create_engine(os.environ["DATABASE_URL"])
schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db", "users_schema.sql")
with open(schema_path) as f:
    schema_sql = f.read()

with engine.begin() as conn:
    conn.execute(text(schema_sql))
    exists = conn.execute(
        text("SELECT 1 FROM users WHERE username = :u"), {"u": args.username}
    ).fetchone()
    if exists:
        sys.exit(f"User '{args.username}' already exists.")
    conn.execute(
        text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, :r)"),
        {
            "u": args.username,
            "h": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            "r": args.role,
        },
    )

print(f"Created {args.role} user '{args.username}'.")