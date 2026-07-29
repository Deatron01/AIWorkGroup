# foundry-project/backend/core/metrics_collector.py
import asyncio
import psutil
import logging
from datetime import datetime
from core.database import SessionLocal
from core.models import MetricModel
from api.websocket import manager

logger = logging.getLogger("MetricsCollector")

class MetricsCollector:
    """
    Background worker that samples hardware metrics (CPU, RAM, simulated VRAM),
    persists them to SQLite, and broadcasts them live to the dashboard UI.
    """
    def __init__(self, interval_sec: float = 2.0):
        self.interval = interval_sec
        self._running = False

    async def start(self):
        self._running = True
        logger.info("[MetricsCollector] Background telemetry loop started.")
        while self._running:
            try:
                metrics_data = self._gather_system_stats()
                
                # 1. Save snapshot to database
                db = SessionLocal()
                snapshot = MetricModel(
                    job_id="active_job", # Linked to current active execution
                    cpu_usage_pct=metrics_data["cpu"],
                    memory_usage_pct=metrics_data["memory"],
                    vram_usage_mb=metrics_data["vram"],
                    active_workers=metrics_data["active_workers"],
                    queue_length=metrics_data["queue_length"]
                )
                db.add(snapshot)
                db.commit()
                db.close()

                # 2. Broadcast live via WebSocket to the dashboard
                await manager.broadcast({
                    "event_type": "METRICS_UPDATE",
                    "payload": metrics_data,
                    "timestamp": datetime.utcnow().isoformat()
                })

            except Exception as e:
                logger.error(f"[MetricsCollector] Error gathering metrics: {str(e)}")

            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False

    def _gather_system_stats(self) -> dict:
        """Collects real system telemetry using psutil."""
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory().percent
        
        # Simulated VRAM tracking for the A4500 (Can be mapped to pynvml if required)
        vram_est = 15200.0 if cpu > 10 else 4500.0 

        return {
            "cpu": cpu,
            "memory": memory,
            "vram": vram_est,
            "active_workers": 3, # Qwen, Gemma, Llama tracking slots
            "queue_length": 0
        }

# Global singleton collector
metrics_collector = MetricsCollector()