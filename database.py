import asyncpg
import datetime
from config import DATABASE_URL

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            expiry TIMESTAMP NOT NULL,
            payment_method TEXT,  -- 'stripe', 'paypal', 'crypto'
            active BOOLEAN DEFAULT TRUE
        )
    ''')
    await conn.close()

async def add_or_update_subscription(user_id: int, username: str, months: int = 1, method: str = "manual"):
    expiry = datetime.datetime.utcnow() + datetime.timedelta(days=30 * months)
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        INSERT INTO subscriptions (user_id, username, expiry, payment_method, active)
        VALUES ($1, $2, $3, $4, TRUE)
        ON CONFLICT (user_id) DO UPDATE SET
            username = EXCLUDED.username,
            expiry = EXCLUDED.expiry,
            payment_method = EXCLUDED.payment_method,
            active = TRUE
    ''', user_id, username, expiry, method)
    await conn.close()
    return expiry

async def get_near_expiry(days_list=[1, 3]):
    conn = await asyncpg.connect(DATABASE_URL)
    query = '''
        SELECT user_id, username, 
               (expiry::date - CURRENT_DATE) AS days_left
        FROM subscriptions
        WHERE active = TRUE
          AND (expiry::date - CURRENT_DATE) = ANY($1::int[])
        ORDER BY days_left
    '''
    rows = await conn.fetch(query, days_list)
    await conn.close()
    return [(row['user_id'], row['username'] or f"ID{row['user_id']}", row['days_left']) for row in rows]

async def get_expired_today():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch('''
        SELECT user_id, username
        FROM subscriptions
        WHERE active = TRUE
          AND expiry::date = CURRENT_DATE
    ''')
    await conn.close()
    return [(row['user_id'], row['username'] or f"ID{row['user_id']}") for row in rows]

async def get_overdue(days=7):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch('''
        SELECT user_id, username
        FROM subscriptions
        WHERE active = TRUE
          AND expiry < CURRENT_TIMESTAMP - INTERVAL '%s days'
    ''', days)
    await conn.close()
    return [(row['user_id'], row['username'] or f"ID{row['user_id']}") for row in rows]