"""
=========================================
Logger FiscalPro
=========================================
"""

import logging
from pathlib import Path

from .config import LOG_DIR

Path(LOG_DIR).mkdir(exist_ok=True)

logging.basicConfig(
    filename=f"{LOG_DIR}/fiscalpro.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)

logger = logging.getLogger("FiscalPro")