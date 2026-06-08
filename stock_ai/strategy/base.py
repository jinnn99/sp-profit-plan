"""전략 인터페이스.

전략은 OHLCV(+지표) 데이터프레임을 받아 '목표 포지션' Series 를 돌려준다.
    - 1.0  = 풀 매수(롱)
    - 0.0  = 현금(미보유)
신호는 그날 종가까지의 정보로 계산하고, 백테스트 엔진이 '다음 봉 시가'에
체결하므로 미래참조 편향이 생기지 않는다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """모든 전략의 베이스 클래스."""

    name: str = "base"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """목표 포지션 Series(0.0~1.0)를 반환한다.

        Args:
            df: open/high/low/close/volume 인덱스=date 데이터프레임.

        Returns:
            df.index 와 같은 인덱스의 목표 포지션(0.0 또는 1.0).
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 편의용
        return f"<Strategy {self.name}>"
