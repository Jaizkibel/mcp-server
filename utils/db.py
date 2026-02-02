from contextlib import asynccontextmanager
import logging
import asyncpg
import aioodbc  # For SQL Server connections

logger = logging.getLogger(__name__)

# Global database connection pools
_db_pools = {}

ACCESS_FULL = "full"
ACCESS_READONLY = "readonly"


async def get_db_pool(dbname: str, config: dict, read_only: bool):
    """Get or create a shared database connection pool based on vendor type."""
    poolname, access_level = get_poolname(dbname, read_only)

    if poolname not in _db_pools:
        vendor = config["database"][dbname].get("vendor", "postgresql").lower()

        if vendor == "postgresql":
            _db_pools[poolname] = asyncpg.create_pool(
                user=config["database"][dbname][access_level]["username"],
                password=config["database"][dbname][access_level]["password"],
                database=config["database"][dbname]["dbname"],
                host=config["database"][dbname]["host"],
                port=config["database"][dbname]["port"],
                min_size=config["database"]["min_size"],
                max_size=config["database"]["max_size"],
                max_queries=config["database"]["max_queries"],
                max_inactive_connection_lifetime=config["database"][
                    "max_inactive_connection_lifetime"
                ],
            )
        elif vendor == "sqlserver":
            # Connection string for SQL Server
            # Note: Connection timeouts help detect broken connections faster
            dsn = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={config['database'][dbname]['host']},{config['database'][dbname]['port']};"
                f"DATABASE={config['database'][dbname]['dbname']};"
                f"UID={config['database'][dbname][access_level]['username']};"
                f"PWD={config['database'][dbname][access_level]['password']};"
                f"TrustServerCertificate=yes;"  # Ignore certificate verification errors
                f"Connection Timeout=30;"  # Connection establishment timeout
                f"Mars_Connection=yes;"  # Multiple Active Result Sets
            )

            _db_pools[poolname] = await aioodbc.create_pool(
                dsn=dsn,
                minsize=config["database"]["min_size"],
                maxsize=config["database"]["max_size"],
                autocommit=True,
                timeout=30,  # Pool connection timeout in seconds
            )
        else:
            raise ValueError(f"Unsupported database vendor: {vendor}")

    return _db_pools[poolname]


@asynccontextmanager
async def db_connection_context(dbname: str, config: dict, read_only: bool):
    """Context manager for database operations using connection pool."""
    conn = None

    poolname = f"${dbname}_{ACCESS_READONLY if read_only else ACCESS_FULL}"
    try:
        pool = await get_db_pool(dbname, config, read_only)

        conn = await pool.acquire()
        yield conn
    except Exception as e:
        logger.error("Database error: %s", e, exc_info=True)
        raise
    finally:
        if conn:
            pool = _db_pools.get(poolname)
            if pool:
                await pool.release(conn)


async def close_db_pool():
    """Close all database connection pools."""
    for _, pool in _db_pools.items():
        try:
            await pool.close()
        except Exception as e:
            logger.error("Error closing database pool: %s", e, exc_info=True)
    _db_pools.clear()

def get_poolname(dbname: str, read_only: bool) -> tuple[str, str]:
    if read_only:
        access_level = "readonly"
    else:
        access_level = "full"
    poolname = f"{dbname}_{access_level}"

    return poolname, access_level
