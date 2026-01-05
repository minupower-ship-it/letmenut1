import asyncpg
import datetime
from config import DATABASE_URL

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    # 기본 테이블 생성
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS members (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            is_lifetime BOOLEAN DEFAULT FALSE,
            expiry TIMESTAMP,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS daily_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            action TEXT,
            amount DECIMAL DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # language 컬럼이 없으면 추가 (기존 DB에도 안전하게 적용)
    try:
        await conn.execute('ALTER TABLE members ADD COLUMN language TEXT DEFAULT \'EN\';')
    except asyncpg.DuplicateColumnError:
        pass  # 이미 있으면 무시

    await conn.close()

# 나머지 함수들은 이전과 동일
async def add_member(user_id, username, customer_id=None, subscription_id=None, is_lifetime=False, language='EN'):
    expiry = None if is_lifetime else (datetime.datetime.utcnow() + datetime.timedelta(days=30))
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        INSERT INTO members (user_id, username, stripe_customer_id, stripe_subscription_id, is_lifetime, expiry, active, language)
        VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
        ON CONFLICT (user_id) DO UPDATE SET
            username = EXCLUDED.username,
            stripe_customer_id = COALESCE(EXCLUDED.stripe_customer_id, members.stripe_customer_id),
            stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, members.stripe_subscription_id),
            is_lifetime = members.is_lifetime OR EXCLUDED.is_lifetime,
            expiry = EXCLUDED.expiry,
            active = TRUE,
            language = COALESCE(EXCLUDED.language, members.language)
    ''', user_id, username, customer_id, subscription_id, is_lifetime, expiry, language)
    await conn.close()

async def log_action(user_id, action, amount=0):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('INSERT INTO daily_logs (user_id, action, amount) VALUES ($1, $2, $3)', user_id, action, amount)
    await conn.close()

async def get_member_status(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('''
        SELECT username, stripe_customer_id, is_lifetime, expiry, created_at, language
        FROM members WHERE user_id = $1 AND active = TRUE
    ''', user_id)
    await conn.close()
    return row

async def get_near_expiry():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch('''
        SELECT user_id, username, (expiry::date - CURRENT_DATE) AS days_left
        FROM members
        WHERE active = TRUE AND NOT is_lifetime AND (expiry::date - CURRENT_DATE) IN (1, 3)
    ''')
    await conn.close()
    return [(r['user_id'], r['username'] or f"ID{r['user_id']}", r['days_left']) for r in rows]

async def get_expired_today():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch('''
        SELECT user_id, username FROM members
        WHERE active = TRUE AND NOT is_lifetime AND expiry::date = CURRENT_DATE
    ''')
    await conn.close()
    return [(r['user_id'], r['username'] or f"ID{r['user_id']}") for r in rows]

async def get_daily_stats():
    conn = await asyncpg.connect(DATABASE_URL)
    today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await conn.fetch('''
        SELECT COUNT(DISTINCT user_id) AS unique_users,
               SUM(amount) FILTER (WHERE action LIKE 'payment_stripe%') AS total_revenue
        FROM daily_logs
        WHERE timestamp >= $1
    ''', today)
    await conn.close()
    return rows[0] if rows else {'unique_users': 0, 'total_revenue': 0}
