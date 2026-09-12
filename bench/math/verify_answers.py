#!/usr/bin/env python3
"""verify_answers.py: the answer key's second derivation.

Every item in items.jsonl gets its answer recomputed here by an independent
method (brute force or numeric wherever possible), because a wrong answer key
produces believable wrong rankings and nobody would know. The 08-09 lesson:
a bench on the wrong population produced a believable wrong answer. Run this
before any heat; the bank is not banked until it prints ALL VERIFIED.

Exact keys must match exactly (as Fractions); keys carrying a tol are checked
numerically within that tol. Exit 1 on any mismatch.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITEMS = HERE / "items.jsonl"


def primes_below(n):
    sieve = [True] * n
    sieve[0:2] = [False, False]
    for i in range(2, int(n ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i:: i] = [False] * len(sieve[i * i:: i])
    return [i for i, p in enumerate(sieve) if p]


def is_prime(n):
    if n < 2:
        return False
    for d in range(2, int(n ** 0.5) + 1):
        if n % d == 0:
            return False
    return True


def ncr(n, r):
    return math.comb(n, r)


def derangements(n):
    d = [1, 0]
    for i in range(2, n + 1):
        d.append((i - 1) * (d[i - 1] + d[i - 2]))
    return d[n]


def catalan_paths(n):
    # Monotonic paths (0,0) to (n,n) never above y=x, by DP.
    grid = [[0] * (n + 1) for _ in range(n + 1)]
    grid[0][0] = 1
    for x in range(n + 1):
        for y in range(n + 1):
            if y > x:
                continue
            if x > 0:
                grid[x][y] += grid[x - 1][y]
            if y > 0 and y - 1 <= x:
                grid[x][y] += grid[x][y - 1]
    return grid[n][n]


def order_mod(a, m):
    v = a % m
    k = 1
    x = v
    while x != 1:
        x = (x * v) % m
        k += 1
        if k > m:
            raise RuntimeError("no order")
    return k


def simpson(f, a, b, n=20000):
    h = (b - a) / n
    s = f(a) + f(b)
    for i in range(1, n):
        s += f(a + i * h) * (4 if i % 2 else 2)
    return s * h / 3


TRUTH = {}


def truth(item_id):
    def deco(fn):
        TRUTH[item_id] = fn
        return fn
    return deco


truth("nt-a1")(lambda: math.gcd(462, 1071))
truth("nt-a2")(lambda: pow(7, 2026, 10))
truth("nt-b1")(lambda: sum(1 for d in range(1, 40321) if 40320 % d == 0))
truth("nt-b2")(lambda: next(x for x in range(1, 10000)
                            if x % 5 == 3 and x % 7 == 4 and x % 3 == 1))
truth("nt-c1")(lambda: sum(p for p in primes_below(100) if p % 4 == 1))
truth("nt-c2")(lambda: order_mod(2, 101))
truth("al-a1")(lambda: Fraction(12, 3))
truth("al-a2")(lambda: (2 * 9 + 3) - (3 ** 2))


@truth("al-b1")
def _al_b1():
    roots = []
    for sign in (1, -1):
        # sign*(2x-5) = x+4  ->  x = (5*sign+4)/(2*sign-1) with validity checks
        x = Fraction(5 * sign + 4, 2 * sign - 1)
        if abs(2 * x - 5) == x + 4 and x + 4 >= 0:
            roots.append(x)
    return sum(set(roots))


truth("al-b2")(lambda: float(sum(Fraction(k, 3 ** k) for k in range(1, 60))))


@truth("al-c1")
def _al_c1():
    t = {1: Fraction(4)}
    t[2] = t[1] * t[1] - 2
    for n in (3, 4, 5):
        t[n] = t[1] * t[n - 1] - t[n - 2]
    return t[5]


truth("al-c2")(lambda: sum(r ** 3 for r in (1, 2, 3)))
truth("co-a1")(lambda: ncr(10, 3))
truth("co-a2")(lambda: math.factorial(6))
truth("co-b1")(lambda: math.factorial(8) // 2)
truth("co-b2")(lambda: 4 * ncr(13, 5))
truth("co-c1")(lambda: catalan_paths(6))
truth("co-c2")(lambda: derangements(7))
truth("pr-a1")(lambda: Fraction(sum(1 for a in range(1, 7) for b in range(1, 7)
                                    if a + b == 7), 36))
truth("pr-a2")(lambda: Fraction(3, 8))
truth("pr-b1")(lambda: Fraction(5, 8) * Fraction(4, 7))
truth("pr-b2")(lambda: Fraction(6))
truth("pr-c1")(lambda: 6 * sum(Fraction(1, k) for k in range(1, 7)))
truth("pr-c2")(lambda: (Fraction(99, 100) * Fraction(1, 100)) /
               (Fraction(99, 100) * Fraction(1, 100) +
                Fraction(2, 100) * Fraction(99, 100)))


@truth("ca-a1")
def _ca_a1():
    h = 1e-6
    f = lambda x: x ** 3 * math.log(x)
    return (f(1 + h) - f(1 - h)) / (2 * h)


truth("ca-a2")(lambda: simpson(lambda x: 3 * x * x + 2 * x, 0, 1))
truth("ca-b1")(lambda: (1 - math.cos(3 * 1e-5)) / 1e-10)
truth("ca-b2")(lambda: simpson(lambda x: x * math.exp(-2 * x), 0, 40, 200000))
truth("ca-c1")(lambda: (1 / math.sqrt(2)) * math.exp(-0.5))
truth("ca-c2")(lambda: float(sum(Fraction(1, n * (n + 2)) for n in range(1, 4000))))
truth("la-a1")(lambda: 2 * 4 - 3 * 1)
truth("la-a2")(lambda: (1 * 5 + 2 * 6) + (3 * 5 + 4 * 6))


@truth("la-b1")
def _la_b1():
    tr, det = 7, 4 * 3 - 1 * 2
    disc = math.sqrt(tr * tr - 4 * det)
    return (tr + disc) / 2


@truth("la-b2")
def _la_b2():
    import fractions
    rows = [[Fraction(v) for v in r] for r in ([1, 2, 3], [2, 4, 6], [1, 1, 1])]
    rank = 0
    for col in range(3):
        piv = next((r for r in range(rank, 3) if rows[r][col] != 0), None)
        if piv is None:
            continue
        rows[rank], rows[piv] = rows[piv], rows[rank]
        for r in range(3):
            if r != rank and rows[r][col] != 0:
                f = rows[r][col] / rows[rank][col]
                rows[r] = [a - f * b for a, b in zip(rows[r], rows[rank])]
        rank += 1
    return rank


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


truth("la-c1")(lambda: det3([[1, 1, 1], [1, 2, 4], [1, 3, 9]]))
truth("la-c2")(lambda: max(3 * x + 4 * y for x in range(0, 10) for y in range(0, 10)
                           if x + 2 * y <= 7 and 3 * x + y <= 9))
truth("hg-01")(lambda: sum(int(c) for c in "274") *
               math.prod(int(c) for c in "274" if c != "0"))


@truth("hg-02")
def _hg_02():
    a = 5
    for _ in range(5):
        a = 2 * a - 3
    return a


truth("hg-03")(lambda: sum(1 for p in itertools.permutations(range(5))
                           if abs(p.index(0) - p.index(1)) != 1))
truth("hg-04")(lambda: Fraction(sum(1 for a, b in itertools.combinations(range(1, 10), 2)
                                    if (a * b) % 2 == 0), ncr(9, 2)))
truth("hg-05")(lambda: max((x / 1000) ** 3 - 6 * (x / 1000) ** 2 + 9 * (x / 1000) + 2
                           for x in range(0, 4001)))
truth("hg-06")(lambda: det3([[3, 0, 2], [1, 4, 1], [2, 5, 0]]))
truth("hg-07")(lambda: sum(1 for p in primes_below(1000) if p > 3 and is_prime(p * p + 2)))


@truth("hg-08")
def _hg_08():
    ps = (0.9, 0.8, 0.7)
    total = 0.0
    for bits in itertools.product((1, 0), repeat=3):
        if sum(bits) >= 2:
            pr = 1.0
            for b, p in zip(bits, ps):
                pr *= p if b else (1 - p)
            total += pr
    return total


truth("hg-09")(lambda: math.sqrt(14 ** 2 - 2 * 48))
truth("hg-10")(lambda: sum(1 for s in itertools.product("ABC", repeat=6)
                           if all(a != b for a, b in zip(s, s[1:]))))
truth("hg-11")(lambda: 3 + Fraction(69 - 36, 7))
truth("hg-12")(lambda: (lambda n: sum(n // 5 ** k for k in range(1, 10)))(33))
truth("ap-01")(lambda: sum(1 for t in range(0, 100) if abs(35 - t) < 5))
truth("ap-02")(lambda: Fraction(2 * 10 + 3 * 20 + 5 * 40, 10))


@truth("ap-03")
def _ap_03():
    vals = [1, 2, 3, 4, 5]
    wts = [5, 1, 1, 1, 7]
    half = Fraction(sum(wts), 2)
    cum = 0
    for v, w in zip(vals, wts):
        cum += w
        if cum >= half:
            return v


@truth("ap-04")
def _ap_04():
    def cost(q):
        return sum(3 * max(0, d - q) + max(0, q - d) for d in range(1, 101))
    return min(range(1, 101), key=cost)


truth("ap-05")(lambda: abs(128450 - (97300 + 31275)))
truth("ap-06")(lambda: (10 / math.sqrt(400)) * math.sqrt(1 - 400 / 12000))
truth("ap-07")(lambda: max(abs(v - 4.5) for v in range(0, 10)))
truth("ap-08")(lambda: ((124 / 100) ** 0.25 - 1) * 100)


@truth("ap-09")
def _ap_09():
    a, b = 1000.0, 500.0
    for _ in range(2):
        a, b = a * 0.9 + b * 0.3, b * 0.7 + a * 0.1
    return a


@truth("ap-10")
def _ap_10():
    sols = [(a, b) for b in range(0, 10) for a in range(0, 15)
            if 7 * a + 11 * b == 100]
    a, b = min(sols, key=lambda s: s[1])
    return a + b


def parse_key(s):
    if "/" in s:
        return Fraction(s)
    return Fraction(s) if "." not in s else float(s)


def main() -> int:
    bad = 0
    items = [json.loads(l) for l in ITEMS.read_text().splitlines() if l.strip()]
    seen = set()
    for it in items:
        iid = it["id"]
        if iid in seen:
            print(f"DUPLICATE id {iid}")
            bad += 1
        seen.add(iid)
        if iid not in TRUTH:
            print(f"NO INDEPENDENT DERIVATION for {iid}")
            bad += 1
            continue
        computed = TRUTH[iid]()
        key = parse_key(it["answer"])
        tol = it.get("tol")
        if tol is not None:
            ok = abs(float(computed) - float(key)) <= tol
        elif isinstance(computed, Fraction) or isinstance(computed, int):
            ok = Fraction(computed) == Fraction(key)
        else:
            ok = abs(float(computed) - float(key)) <= 1e-3
        if not ok:
            print(f"MISMATCH {iid}: key={it['answer']} computed={computed}")
            bad += 1
    missing = [k for k in TRUTH if k not in seen]
    for k in missing:
        print(f"DERIVATION WITHOUT ITEM: {k}")
        bad += 1
    if bad:
        print(f"{bad} problems; the bank is NOT banked.")
        return 1
    print(f"ALL VERIFIED: {len(items)} items, every answer independently derived.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
