"""리포트 계층 — 성과 지표 계산과 HTML 리포트 생성."""

from stock_ai.report.metrics import compute_metrics
from stock_ai.report.html_report import build_html_report

__all__ = ["compute_metrics", "build_html_report"]
