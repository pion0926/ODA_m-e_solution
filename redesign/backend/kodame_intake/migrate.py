"""Apply idempotent schema changes before starting the API and workers."""
from .db import migrate_database

if __name__ == '__main__':
    migrate_database()
    print('Database migrations completed.', flush=True)
