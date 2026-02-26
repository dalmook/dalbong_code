import math
import re
from dataclasses import dataclass
from statistics import median
from typing import Optional


PRICE_RE = re.compile(r"([0-9][0-9,]{2,})\s*원")
COUNT_PATTERNS = [
    re.compile(r"(?<!\d)(\d{1,4})\s*(?:개입|개)\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(\d{1,4})\s*입\b", re.IGNORECASE),
]


def _to_int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _clean_title_for_key(title: str) -> str:
    text = (title or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = PRICE_RE.sub(" ", text)
    text = re.sub(r"\b(무료배송|무배|배송비포함|배송비|카드|쿠폰|적립)\b", " ", text)
    text = re.sub(r"[^0-9a-zA-Z가-힣\s/]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120]


def _extract_count(title: str) -> Optional[int]:
    for pattern in COUNT_PATTERNS:
        match = pattern.search(title or "")
        if not match:
            continue
        try:
            count = int(match.group(1))
        except ValueError:
            continue
        if 1 <= count <= 5000:
            return count
    return None


def _format_krw(value: float) -> str:
    if math.isclose(value, round(value), rel_tol=0, abs_tol=1e-9):
        return f"{int(round(value)):,}원"
    return f"{value:,.1f}원"


@dataclass
class PriceObservation:
    item_id: str
    title: str
    link: str
    board_rss_url: str
    source: str
    total_price_krw: Optional[int]
    quantity_count: Optional[int]
    metric_value_krw: Optional[float]
    metric_basis: Optional[str]
    product_key: Optional[str]
    crawled_at: Optional[str] = None
    published_at: Optional[str] = None

    @property
    def metric_text(self) -> Optional[str]:
        if self.metric_value_krw is None:
            return None
        if self.metric_basis == "ea":
            return f"{_format_krw(self.metric_value_krw)}/개"
        if self.metric_basis == "total":
            return _format_krw(self.metric_value_krw)
        return _format_krw(self.metric_value_krw)


@dataclass
class PriceAnalysis:
    metric_text: str
    compare_text: str
    verdict: str

    def to_alert_line(self) -> str:
        return f"💹 분석: {self.metric_text} ({self.compare_text}, {self.verdict})"


def parse_price_observation(
    *,
    item_id: str,
    title: str,
    link: str,
    board_rss_url: str,
    source: str = "rss",
    published_at: Optional[str] = None,
    crawled_at: Optional[str] = None,
) -> Optional[PriceObservation]:
    prices = [_to_int(m.group(1)) for m in PRICE_RE.finditer(title or "")]
    prices = [p for p in prices if p is not None]
    if not prices:
        return None

    total_price = prices[-1]
    count = _extract_count(title or "")
    metric_value = float(total_price)
    metric_basis = "total"
    if count and count > 0:
        metric_value = total_price / count
        metric_basis = "ea"

    product_key = _clean_title_for_key(title or "")
    if not product_key:
        product_key = None

    return PriceObservation(
        item_id=item_id,
        title=title,
        link=link,
        board_rss_url=board_rss_url,
        source=source,
        total_price_krw=total_price,
        quantity_count=count,
        metric_value_krw=metric_value,
        metric_basis=metric_basis,
        product_key=product_key,
        published_at=published_at,
        crawled_at=crawled_at,
    )


def build_price_analysis(
    current_value: Optional[float],
    basis: Optional[str],
    previous_values: list[float],
) -> Optional[PriceAnalysis]:
    if current_value is None or not basis or not previous_values:
        return None
    prev_last = previous_values[-1]
    prev_med = median(previous_values)

    diff = current_value - prev_last
    pct = (diff / prev_last * 100.0) if prev_last else 0.0
    sign = "+" if diff > 0 else ""
    basis_suffix = "/개" if basis == "ea" else ""
    metric_text = f"{_format_krw(current_value)}{basis_suffix}"
    compare_text = f"직전 { _format_krw(prev_last) }{basis_suffix} 대비 {sign}{_format_krw(diff)} ({sign}{pct:.1f}%)"

    if current_value <= min(previous_values) * 1.01:
        verdict = "저렴"
    elif current_value >= max(previous_values) * 0.99:
        verdict = "비쌈"
    elif current_value > prev_med * 1.05:
        verdict = "다소 비쌈"
    elif current_value < prev_med * 0.95:
        verdict = "다소 저렴"
    else:
        verdict = "보통"

    return PriceAnalysis(metric_text=metric_text, compare_text=compare_text, verdict=verdict)

