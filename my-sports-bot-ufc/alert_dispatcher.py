"""Bounded alert workers with a local pending-job spool (no delivery retries)."""

import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import time
import uuid


class AlertDispatcher:
    def __init__(self, handler, spool_dir, *, workers=4, capacity=128):
        if workers < 1 or capacity < 1:
            raise ValueError("Alert workers and queue capacity must be positive")
        self.handler = handler
        self.directory = Path(spool_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.queue = Queue(maxsize=capacity)
        self.stop = threading.Event()
        self.threads = [threading.Thread(target=self._worker, daemon=True,
                                        name=f"ufc-alert-{i}") for i in range(workers)]
        for thread in self.threads:
            thread.start()

    def submit(self, job):
        """Save a snapshot, then notify a worker without waiting for queue space."""
        path = self.directory / f"{uuid.uuid4().hex}.json"
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(job), encoding="utf-8")
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError) as exc:
            print(f"[ERROR] Alert could not be saved; manual recovery required: {exc}; job={job!r}")
            return False
        try:
            self.queue.put_nowait(path)
        except Full:
            # Workers discover saved pending jobs when the memory queue drains.
            print(f"[WARN] Alert queue full; job deferred on disk: {path}")
        return True

    def _worker(self):
        while not self.stop.is_set():
            queued = False
            try:
                try:
                    path = self.queue.get(timeout=0.1)
                    queued = True
                except Empty:
                    path = next(self.directory.glob("*.json"), None)
                    if path is None:
                        continue
                claimed = path.with_suffix(".inflight")
                try:
                    # Atomic claim prevents queue hints and disk scans delivering
                    # the same saved job twice, including across worker threads.
                    os.replace(path, claimed)
                except FileNotFoundError:
                    continue
                job = json.loads(claimed.read_text(encoding="utf-8"))
                if self.handler(job) is False:
                    print(f"[WARN] Alert delivery unconfirmed; no automatic retry; inspect {claimed}")
                else:
                    claimed.unlink()
            except Exception as exc:
                # Never replay a claimed job: an external POST may have succeeded.
                # Leave .inflight evidence for manual inspection if delivery raised.
                print(f"[ERROR] Alert worker failed; no automatic retry: {exc}")
                self.stop.wait(0.1)
            finally:
                if queued:
                    self.queue.task_done()

    def close(self, timeout=2):
        """Stop workers; unclaimed disk jobs survive for the next run."""
        self.stop.set()
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        # An active daemon worker may finish after this bounded shutdown wait.
        # If interrupted, its .inflight job must not be automatically reposted.
