"""Container liveness check for worker polling/maintenance loops."""
import sys
import time
from pathlib import Path

if __name__ == '__main__':
    path = Path('/tmp/kodame-' + sys.argv[1] + '-heartbeat')
    sys.exit(0 if path.exists() and time.time()-path.stat().st_mtime < 90 else 1)
