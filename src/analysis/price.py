"""
价格分析模块

分析维度:
- 价格分布 (区间统计)
- 价格对比 (最低/最高/平均)
- 折扣分析 (原价 vs 现价)
- 价格区间商品分布
"""

from typing import List

import pandas as pd


def analyze_price_distribution(products: list[dict]) -> dict:
    """
    价格分布分析

    Returns:
        {
            "min_price": 最低价,
            "max_price": 最高价,
            "mean_price": 平均价,
            "median_price": 中位数,
            "price_ranges": [{"range": "0-50", "count": 10}, ...],
            "top_cheapest": [...]  # 最便宜Top5
        }
    """
    if not products:
        return {"error": "无商品数据"}

    df = pd.DataFrame(products)
    if "price" not in df.columns:
        return {"error": "无价格数据"}

    prices = df["price"].dropna()

    if prices.empty:
        return {"error": "无价格数据"}

    # 基本统计
    stats = {
        "min_price": float(prices.min()),
        "max_price": float(prices.max()),
        "mean_price": round(float(prices.mean()), 2),
        "median_price": float(prices.median()),
        "std_price": round(float(prices.std()), 2),
        "total_products": len(products),
    }

    # 价格区间分布
    bins = _get_price_bins(prices)
    stats["price_ranges"] = bins

    # 折扣分析
    if "original_price" in df.columns:
        has_both = df[df["price"].notna() & df["original_price"].notna()]
        if not has_both.empty:
            has_both = has_both.copy()
            has_both["discount"] = (
                (has_both["original_price"] - has_both["price"])
                / has_both["original_price"] * 100
            )
            stats["avg_discount"] = round(float(has_both["discount"].mean()), 1)
            stats["max_discount"] = round(float(has_both["discount"].max()), 1)

    # 最便宜/最贵 Top5
    df_sorted = df.sort_values("price")
    stats["top_cheapest"] = _pick_top(df_sorted, 5, ascending=True)
    stats["top_expensive"] = _pick_top(df_sorted, 5, ascending=False)

    return stats


def _get_price_bins(prices: pd.Series) -> list[dict]:
    """动态计算价格区间"""
    pmin, pmax = prices.min(), prices.max()
    if pmin == pmax:
        return [{"range": f"¥{pmin:.0f}", "count": len(prices)}]

    # 根据价格范围选择区间粒度
    span = pmax - pmin
    if span <= 100:
        step = 20
    elif span <= 500:
        step = 50
    elif span <= 2000:
        step = 200
    elif span <= 10000:
        step = 1000
    else:
        step = 2000

    bin_edges = list(range(int(pmin // step) * step, int(pmax) + step, step))
    bin_edges = [b for b in bin_edges if b <= pmax + step][:10]  # 最多10个区间

    if len(bin_edges) < 2:
        return [{"range": f"¥{pmin:.0f}-¥{pmax:.0f}", "count": len(prices)}]

    labels = [f"¥{bin_edges[i]}-¥{bin_edges[i+1]}" for i in range(len(bin_edges) - 1)]
    cuts = pd.cut(prices, bins=bin_edges, labels=labels, include_lowest=True)
    counts = cuts.value_counts().sort_index()

    return [{"range": str(k), "count": int(v)} for k, v in counts.items()]


def _pick_top(df: pd.DataFrame, n: int, ascending: bool = True) -> list[dict]:
    """选取 Top N 商品"""
    subset = df.sort_values("price", ascending=ascending).head(n)
    return [
        {
            "title": row.get("title", "")[:40],
            "price": row.get("price"),
            "shop_name": row.get("shop_name", ""),
            "url": row.get("url", ""),
        }
        for _, row in subset.iterrows()
    ]
