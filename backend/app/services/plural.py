"""Русское склонение существительных по числу: plural(2, 'пациент','пациента','пациентов')."""


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many


def count(n: int, one: str, few: str, many: str) -> str:
    """«3 пациента» — число + правильная форма слова."""
    return f"{n} {plural(n, one, few, many)}"
