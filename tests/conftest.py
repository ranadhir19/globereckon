import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["GLOBERECKON_FIXTURES"] = "1"  # API tests run on labelled fixtures
