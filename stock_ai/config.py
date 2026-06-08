"""전역 설정 — .env 파일에서 API 키·경로를 읽는다.

pydantic-settings 를 써서 .env 의 값을 타입 안전하게 로드한다.
설정값은 `from stock_ai.config import settings` 로 어디서나 가져다 쓴다.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 프로젝트 루트 (이 파일 기준 상위 폴더)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """앱 전역 설정. .env 의 같은 이름 변수로 덮어쓸 수 있다."""

    # SEC EDGAR 는 호출 시 식별용 User-Agent 를 요구한다(이메일 권장). .env 로 바꿀 수 있다.
    # 참고: https://www.sec.gov/os/webmaster-faq#developers
    sec_user_agent: str = "stock-ai-research jz.research@example.com"

    # (선택) Finnhub 무료 키 — 없으면 yfinance 뉴스만 사용
    finnhub_api_key: str = ""

    # FinBERT 모델 이름 (무료 로컬 감성분석)
    finbert_model: str = "ProsusAI/finbert"

    # 저장 경로 (프로젝트 루트 기준 상대경로)
    data_cache_dir: str = "data_cache"
    reports_dir: str = "reports"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cache_path(self) -> Path:
        """가격 데이터 SQLite 등을 보관하는 폴더 (없으면 생성)."""
        p = PROJECT_ROOT / self.data_cache_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_path(self) -> Path:
        """HTML 리포트를 저장하는 폴더 (없으면 생성)."""
        p = PROJECT_ROOT / self.reports_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        """캐시용 SQLite 파일 경로 (가격·재무·뉴스·감성 테이블 공용)."""
        return self.cache_path / "prices.sqlite"


# 앱 전역에서 공유하는 단일 설정 인스턴스
settings = Settings()


# 5축 종합점수 기본 가중치 (장기투자형: 품질·가치·성장에 무게).
# 합이 1.0 이 되도록 정규화해서 쓴다. CLI 로 일부만 덮어쓸 수 있다.
DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "value": 0.25,      # 가치 (저평가)
    "quality": 0.25,    # 수익성·재무건전성
    "growth": 0.20,     # 성장성
    "trend": 0.20,      # 장기 추세·모멘텀
    "sentiment": 0.10,  # 뉴스 심리
}

# 각 축의 한국어 표기 (리포트용)
FACTOR_LABELS_KO: dict[str, str] = {
    "value": "가치",
    "quality": "품질",
    "growth": "성장",
    "trend": "추세",
    "sentiment": "심리",
}

# 투자 성향별 가중치 프리셋 — CLI --style 로 고른다.
# 합은 자동 정규화되므로 비율만 맞으면 된다.
FACTOR_WEIGHT_PRESETS: dict[str, dict[str, float]] = {
    # 균형(기본): 가치·품질·성장 고르게
    "balanced": dict(DEFAULT_FACTOR_WEIGHTS),
    # 가치: 저평가 우선 (저PER·저PBR)
    "value": {"value": 0.40, "quality": 0.25, "growth": 0.10, "trend": 0.15, "sentiment": 0.10},
    # 성장: 매출·이익 성장 우선
    "growth": {"value": 0.10, "quality": 0.20, "growth": 0.40, "trend": 0.20, "sentiment": 0.10},
    # 배당·안정: 수익성·재무건전성(품질) + 가치 중심
    "dividend": {"value": 0.30, "quality": 0.45, "growth": 0.05, "trend": 0.10, "sentiment": 0.10},
    # 모멘텀: 추세 우선 (장기 상승 종목)
    "momentum": {"value": 0.10, "quality": 0.15, "growth": 0.15, "trend": 0.50, "sentiment": 0.10},
}

# 성향 한국어 설명 (리포트·CLI 표기용)
STYLE_LABELS_KO: dict[str, str] = {
    "balanced": "균형형(가치·품질·성장 고루)",
    "value": "가치형(저평가 우선)",
    "growth": "성장형(매출·이익 성장 우선)",
    "dividend": "배당·안정형(수익성·재무건전성 우선)",
    "momentum": "모멘텀형(장기 상승 추세 우선)",
}
