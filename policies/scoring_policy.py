SOURCE_WEIGHT_HINTS = {
    "hacker news": 12,
    "the github blog": 15,
    "github blog": 15,
    "techcrunch": 6,
    "36kr": 5,
    "wired": 1,
    "mit technology review": 0,
}


def get_effective_limit(base_limit: int, score: float, attempts: int) -> int:
    if attempts < 2:
        return base_limit
    if score >= 85:
        return base_limit
    if score >= 75:
        return max(3, base_limit - 1)
    if score >= 60:
        return max(2, base_limit - 2)
    return 2
