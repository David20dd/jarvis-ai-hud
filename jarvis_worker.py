"""Optional durable worker for PostgreSQL-backed JARVIS maintenance tasks."""
from __future__ import annotations

import logging
import os
import socket
import time
import uuid

from jarvis_core.v82 import DataFoundation, EmbeddingService


logging.basicConfig(level=os.getenv("JARVIS_LOG_LEVEL", "INFO"))
logger = logging.getLogger("jarvis.worker")


def build_foundation() -> DataFoundation:
    embeddings = EmbeddingService(
        os.getenv("JARVIS_EMBEDDING_PROVIDER", "local"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("JARVIS_EMBEDDING_MODEL", "text-embedding-3-small"),
        dimensions=int(os.getenv("JARVIS_EMBEDDING_DIMENSIONS", "256")),
    )
    return DataFoundation(
        database_url=os.getenv("DATABASE_URL", ""),
        sqlite_file=os.getenv("JARVIS_DB_FILE", "jarvis_memory.db"),
        embeddings=embeddings,
        persistent_declared=os.getenv("JARVIS_PERSISTENT_STORAGE", "false").lower() in {"1", "true", "yes"},
    )


def main() -> None:
    foundation = build_foundation()
    foundation.init_schema()
    worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    poll = max(1.0, float(os.getenv("JARVIS_WORKER_POLL_SECONDS", "2")))
    logger.info("Worker %s iniciado con %s", worker_id, foundation.driver)
    try:
        while True:
            task = foundation.claim_next_task(worker_id, lease_seconds=120)
            if not task:
                time.sleep(poll)
                continue
            try:
                foundation.run_maintenance_task(task["session_id"], task["id"])
                logger.info("Tarea %s completada", task["id"])
            except Exception as exc:
                foundation.fail_task(task["session_id"], task["id"], str(exc), retry_delay=15)
                logger.exception("Tarea %s falló", task["id"])
    except KeyboardInterrupt:
        logger.info("Worker detenido")
    finally:
        foundation.close()


if __name__ == "__main__":
    main()
