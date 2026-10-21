"""Create tables. Run once."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.db import init_db

if __name__ == "__main__":
    init_db()
    print("Tables created.")
