from contextlib import asynccontextmanager
import logging
import asyncpg
import aioodbc  # For SQL Server connections

logger = logging.getLogger(__name__)

# Global database connection pools
_db_pools = {}


async def get_db_pool(dbname: str, config: dict):
    """Get or create a shared database connection pool based on vendor type."""
    global _db_pools
    
    if dbname not in _db_pools:
        vendor = config["database"][dbname].get("vendor", "postgresql").lower()
        
        if vendor == "postgresql":
            _db_pools[dbname] = await asyncpg.create_pool(
                user=config["database"][dbname]["username"],
                password=config["database"][dbname]["password"],
                database=config["database"][dbname]["dbname"],
                host=config["database"][dbname]["host"],
                port=config["database"][dbname]["port"],
                min_size=config["database"]["min_size"],
                max_size=config["database"]["max_size"],
                max_queries=config["database"]["max_queries"],
                max_inactive_connection_lifetime=config["database"]["max_inactive_connection_lifetime"]
            )
        elif vendor == "sqlserver":
            # Connection string for SQL Server
            dsn = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={config['database'][dbname]['host']},{config['database'][dbname]['port']};"
                f"DATABASE={config['database'][dbname]['dbname']};"
                f"UID={config['database'][dbname]['username']};"
                f"PWD={config['database'][dbname]['password']};"
                f"TrustServerCertificate=yes;"  # Added to ignore certificate verification errors
            )
            
            _db_pools[dbname] = await aioodbc.create_pool(
                dsn=dsn,
                minsize=config["database"]["min_size"],
                maxsize=config["database"]["max_size"],
                autocommit=False,
            )
        else:
            raise ValueError(f"Unsupported database vendor: {vendor}")
    
    return _db_pools[dbname]

@asynccontextmanager
async def db_connection_context(dbname: str, config: dict):
    """Context manager for database operations using connection pool."""
    conn = None
    try:
        vendor = config["database"][dbname].get("vendor", "postgresql").lower()
        pool = await get_db_pool(dbname, config)
        
        conn = await pool.acquire()
        yield conn
    except Exception as e:
        logger.error(f"Database error: {e}", exc_info=True)
        raise
    finally:
        if conn:
            # Release connection back to pool
            if conn:
                pool = _db_pools.get(dbname)
                if pool:
                    await pool.release(conn)

async def close_db_pool():
    """Close all database connection pools."""
    global _db_pools
    for dbname, pool in _db_pools.items():
        await pool.close()
    _db_pools = {}
