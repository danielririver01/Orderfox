"""Quick test: connect to Supabase PostgreSQL and list tables."""
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
url = os.environ.get('DATABASE_URL', '')
print(f"Driver: {url.split(':')[0] if url else 'NOT SET'}")

try:
    conn = psycopg2.connect(url.replace('postgresql+psycopg2://', 'postgresql://'))
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    )
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables: {len(tables)}")
    for t in tables:
        print(f"  - {t}")
    cur.close()
    conn.close()
    print("CONNECTION OK")
except Exception as e:
    print(f"ERROR: {e}")
