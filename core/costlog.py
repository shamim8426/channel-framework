"""Cost log (CSV per channel) + budget guard. Currency is whatever the channel budget says (default INR); providers report
a number in that currency. Mock providers report 0."""
import csv
import datetime as dt
from pathlib import Path

from .config import ChannelConfig
from .errors import BudgetError
from .paths import Workspace

try:
    import fcntl  # POSIX only; on Windows the append is still a single small write
except ImportError:  # pragma: no cover
    fcntl = None

COLUMNS = ["timestamp", "channel", "project", "provider", "kind", "detail", "cost"]


class CostLog:
    def __init__(self, ws: Workspace, cfg: ChannelConfig):
        self.cfg = cfg
        self.path = ws.channel_dir(cfg.slug) / "cost_log.csv"

    def append(self, project: str, provider: str, kind: str, cost: float, detail: str = ""):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            w = csv.writer(f)
            if new:
                w.writerow(COLUMNS)
            w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), self.cfg.slug, project, provider, kind,
                        detail, f"{cost:.4f}"])

    def total(self, project: str | None = None) -> float:
        if not self.path.exists():
            return 0.0
        with self.path.open(newline="", encoding="utf-8") as f:
            return sum(float(r["cost"]) for r in csv.DictReader(f) if project is None or r["project"] == project)

    def check(self, project: str, estimate: float):
        """Raise BudgetError before a paid call that would push the project over the hard cap."""
        cap = self.cfg["budget"]["hard_cap_per_project"]
        spent = self.total(project)
        if spent + estimate > cap:
            raise BudgetError(f"budget: {spent:.2f} spent + {estimate:.2f} estimate > hard cap {cap} "
                              f"{self.cfg['budget']['currency']} for project {project}. Simplify the plan or raise the cap in config.")
