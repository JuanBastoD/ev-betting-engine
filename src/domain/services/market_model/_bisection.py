"""Private, dependency-free root finder shared by the devig strategies that
have no closed form (Shin, Power).

Plain bisection rather than anything from `scipy` (not a project dependency,
and would be a heavy import for one root-find): correct, deterministic and
fast enough for a handful of market outcomes. Runs a fixed iteration count
rather than an epsilon-based stopping condition, so it is trivially
deterministic and side-effect free - no risk of a pathological input causing
an unbounded loop.
"""

from collections.abc import Callable

_ITERATIONS = 100


def bisect_root(f: Callable[[float], float], lo: float, hi: float) -> float:
    """Find x in [lo, hi] with f(x) ~= 0, given f is monotonic on the
    interval (so f(lo) and f(x) share a sign until the root is crossed).

    100 fixed iterations shrink the bracket by 2**-100 - astronomically
    tighter than double-precision floats can represent - regardless of the
    initial bracket width used by any caller in this module.

    Callers in this module (the no-overround market case) can land the root
    exactly on `lo`; a plain sign-comparison loop mishandles f(lo) == 0.0
    (neither ">0" nor "<0"), so that boundary is checked explicitly first.
    """
    f_lo = f(lo)
    if f_lo == 0.0:
        return lo
    for _ in range(_ITERATIONS):
        mid = (lo + hi) / 2.0
        f_mid = f(mid)
        if (f_mid > 0.0) == (f_lo > 0.0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2.0
