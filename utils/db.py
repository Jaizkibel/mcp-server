from contextlib import asynccontextmanager
import logging
import asyncpg

logger = logging.getLogger(__name__)

# Global database connection pool
_db_pool = None


async def get_db_pool(config) -> asyncpg.pool.Pool:
    """Get or create a shared database connection pool."""
    global _db_pool
    if _db_pool is None:
        dbName = config["dbName"]
        if dbName is None:
            raise ValueError("Database name not specified in configuration")
        _db_pool = await asyncpg.create_pool(
            user=config["database"][dbName]["username"],
            password=config["database"][dbName]["password"],
            database=config["database"][dbName]["dbname"],
            host=config["database"][dbName]["host"],
            port=config["database"][dbName]["port"],
            min_size=config["database"]["min_size"],
            max_size=config["database"]["max_size"],
            max_queries=config["database"]["max_queries"],
            max_inactive_connection_lifetime=config["database"]["max_inactive_connection_lifetime"]
        )
    return _db_pool

@asynccontextmanager
async def db_connection_context(config):
    """Context manager for database operations using connection pool."""
    try:
        pool = await get_db_pool(config=config)
        conn = None
        conn = await pool.acquire()
        yield conn
    except Exception as e:
        logger.error(f"Database error: {e}", exc_info=True)
        raise
    finally:
        if conn:
            await pool.release(conn)

async def close_db_pool():
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None
