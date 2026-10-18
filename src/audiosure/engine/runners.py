from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

from audiosure.engine.pipeline import AuditOptions, AuditResult, run_audit


@dataclass
class RunnerProgressEvent:
    platform: str
    phase: str
    message: str


RunnerProgress = Optional[Callable[[RunnerProgressEvent], None]]


class LocalRunner:
    kind = "local"
    name = "local-runner"

    def __init__(self, on_progress: RunnerProgress = None) -> None:
        self._on_progress = on_progress

    def run(self, options: AuditOptions) -> AuditResult:
        start = time.time()
        if self._on_progress:
            for platform in options.platforms:
                self._on_progress(
                    RunnerProgressEvent(
                        platform=platform, phase="profile", message=f"estimating metrics for {platform}"
                    )
                )
        result = run_audit(options)
        result.report.runner.kind = "local"
        result.report.runner.name = self.name
        result.report.runner.duration_ms = int((time.time() - start) * 1000)
        return result


class CloudRunnerSim:
    kind = "cloud-sim"

    def __init__(
        self,
        region: str = "us-west-2",
        queue_ms_per_platform: int = 400,
        build_ms_per_platform: int = 1200,
        on_progress: RunnerProgress = None,
    ) -> None:
        self.region = region
        self.queue_ms = queue_ms_per_platform
        self.build_ms = build_ms_per_platform
        self._on_progress = on_progress
        self.name = f"cloud-sim:{self.region}"

    def _stage(self, platform: str) -> None:
        if self._on_progress:
            self._on_progress(
                RunnerProgressEvent(platform=platform, phase="queue", message=f"queued on {self.region} runner")
            )
        time.sleep(self.queue_ms / 1000)
        if self._on_progress:
            self._on_progress(
                RunnerProgressEvent(
                    platform=platform, phase="build", message=f"building audio middleware for {platform}"
                )
            )
        time.sleep(self.build_ms / 1000)
        if self._on_progress:
            self._on_progress(
                RunnerProgressEvent(
                    platform=platform, phase="profile", message=f"collecting profiling capture for {platform}"
                )
            )

    def run(self, options: AuditOptions) -> AuditResult:
        start = time.time()
        with ThreadPoolExecutor(max_workers=max(1, len(options.platforms))) as pool:
            list(pool.map(self._stage, options.platforms))

        result = run_audit(options)
        result.report.runner.kind = "cloud-sim"
        result.report.runner.name = self.name
        result.report.runner.duration_ms = int((time.time() - start) * 1000)
        if self._on_progress:
            for platform in options.platforms:
                self._on_progress(
                    RunnerProgressEvent(
                        platform=platform,
                        phase="done",
                        message=f"certification complete for {platform}",
                    )
                )
        return result
