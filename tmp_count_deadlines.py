import sqlite3
from pathlib import Path

path = Path('data/jarvis.db')
conn = sqlite3.connect(path)
cur = conn.cursor()
cur.execute("""
SELECT COUNT(*)
FROM opportunities
WHERE status = 'active'
  AND COALESCE(deadline_text, '') != ''
  AND (
    lower(COALESCE(deadline_text, '')) LIKE '%24/7%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%24х7%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%круглосуточно%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%постоянно%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%без дедлайна%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%без ограничений%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%бессрочно%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%always%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%ongoing%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%rolling%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%continuously%'
    OR lower(COALESCE(deadline_text, '')) LIKE '%открыто всегда%'
  )
""")
print(cur.fetchone()[0])
conn.close()
