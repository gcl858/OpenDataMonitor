import logging
from pathlib import Path
from datetime import datetime

log_dir = Path("logs/history")
log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / f"{datetime.now():%Y-%m-%d}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("opendata-monitor")
