"""Logger central do FiscalPro."""

import logging

from .caminhos import PASTA_LOGS

PASTA_LOGS.mkdir(parents=True, exist_ok=True)
ARQUIVO_LOG = PASTA_LOGS / "fiscalpro.log"

logging.basicConfig(
    filename=str(ARQUIVO_LOG),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)

logger = logging.getLogger("FiscalPro")
