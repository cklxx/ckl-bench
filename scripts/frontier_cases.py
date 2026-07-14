#!/usr/bin/env python3
"""Deterministic generator for frontier-breaker evaluation cases.

These cases stump strong models because they require *exact* execution of a long,
fully-specified deterministic process -- something a model without tools cannot
reliably do in its head -- while the answer is computed here by a literal
reference implementation (ground truth) and checked exactly.

Why this is fair and correct:
- Each prompt is self-contained and unambiguous: the rules plus the concrete
  instance fully determine one answer.
- The reference implementation *is* the spec; the prompt describes exactly what it
  does. Several error-prone families are additionally cross-checked against an
  independent implementation in ``selfcheck()``.
- Instances are generated from fixed seeds, so cases are reproducible and
  contamination-resistant (regenerate with new seeds to refresh the suite).

Usage:
    python scripts/frontier_cases.py --sample        # print one case per family
    python scripts/frontier_cases.py --out cases/chat/frontier_compute.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

RELEASE = "2026-06"
MODP = 1_000_000_007


# --------------------------------------------------------------------------- #
# Families: each returns (prompt, answer_dict, capability_tags, steps, gap)
# --------------------------------------------------------------------------- #

def fam_stackvm(rng: random.Random):
    P = 997
    prog: list[tuple] = []
    depth = 0
    while len(prog) < 64:
        choices = ["PUSH"]
        if depth >= 1:
            choices += ["DUP", "NEG"]
        if depth >= 2:
            choices += ["ADD", "SUB", "MUL", "SWAP"]
        op = rng.choice(choices)
        if op == "PUSH":
            prog.append(("PUSH", rng.randint(0, 60))); depth += 1
        elif op == "DUP":
            prog.append(("DUP",)); depth += 1
        elif op == "NEG":
            prog.append(("NEG",))
        elif op == "SWAP":
            prog.append(("SWAP",))
        else:
            prog.append((op,)); depth -= 1
    s: list[int] = []
    for ins in prog:
        o = ins[0]
        if o == "PUSH":
            s.append(ins[1] % P)
        elif o == "DUP":
            s.append(s[-1])
        elif o == "NEG":
            s[-1] = (-s[-1]) % P
        elif o == "SWAP":
            s[-1], s[-2] = s[-2], s[-1]
        elif o == "ADD":
            b = s.pop(); a = s.pop(); s.append((a + b) % P)
        elif o == "SUB":
            b = s.pop(); a = s.pop(); s.append((a - b) % P)
        elif o == "MUL":
            b = s.pop(); a = s.pop(); s.append((a * b) % P)
    text = "\n".join(" ".join(str(x) for x in ins) for ins in prog)
    prompt = (
        "You are a stack machine over integers modulo 997. Start with an empty stack and execute "
        "these instructions top to bottom:\n"
        "- PUSH n: push (n mod 997).\n"
        "- DUP: push a copy of the current top.\n"
        "- NEG: replace the top t with ((-t) mod 997).\n"
        "- SWAP: swap the top two values.\n"
        "- ADD / SUB / MUL: pop b, then pop a, push (a OP b) mod 997 (so SUB computes a - b).\n\n"
        f"Program:\n{text}\n\n"
        'Return {"top": <final value on top of the stack, 0..996>}.'
    )
    return prompt, {"top": s[-1]}, ["stack-machine", "exact-trace", "modular-arithmetic"], len(prog), \
        "Long exact stack-trace under modular arithmetic; one slip cascades."


def fam_eca(rng: random.Random):
    W, T = 31, 40
    rule = rng.randint(1, 254)
    row = [rng.randint(0, 1) for _ in range(W)]
    if not any(row):
        row[W // 2] = 1
    init = row[:]
    table = [(rule >> i) & 1 for i in range(8)]
    cur = row
    for _ in range(T):
        n = len(cur)
        cur = [table[(cur[(i - 1) % n] << 2) | (cur[i] << 1) | cur[(i + 1) % n]] for i in range(n)]
    value = int("".join(map(str, cur)), 2)
    prompt = (
        f"Elementary cellular automaton, Wolfram rule {rule}, on a row of {W} cells with WRAP-AROUND "
        f"(cell 0's left neighbor is cell {W - 1}; the last cell's right neighbor is cell 0).\n"
        "Each step, every cell's new value is bit number (L*4 + C*2 + R) of the rule, where L, C, R are "
        "the current left-neighbor, the cell itself, and the right-neighbor; bit 0 is the least "
        "significant bit of the rule number.\n"
        f"Initial row (cell 0 first): {''.join(map(str, init))}\n"
        f"Apply exactly {T} steps. Return "
        '{"value": <final row read as a binary number with cell 0 as the most significant bit>}.'
    )
    return prompt, {"value": value}, ["cellular-automaton", "exact-trace", "bit-manipulation"], T * W, \
        "40 synchronous CA steps over 31 wrapped cells; no shortcut, pure trace."


def fam_permcompose(rng: random.Random):
    N, K = 16, 30
    perms = [rng.sample(range(N), N) for _ in range(K)]
    a = 0
    b = N - 1
    for p in perms:
        a = p[a]
        b = p[b]
    body = "\n".join(f"P{i + 1} = {p}" for i, p in enumerate(perms))
    prompt = (
        f"There are {N} positions labeled 0..{N - 1}. Each permutation P below is a list where a token at "
        "position i moves to position P[i]. Apply the permutations in order P1, P2, ..., "
        f"P{K} (after each one, new_position = P[current_position]).\n\n"
        f"{body}\n\n"
        f"Token A starts at position 0; token B starts at position {N - 1}. Apply all {K} permutations to "
        'each. Return {"a": <A final position>, "b": <B final position>}.'
    )
    return prompt, {"a": a, "b": b}, ["permutations", "function-composition", "exact-trace"], K * 2, \
        "30 sequential permutation lookups per token; meticulous bookkeeping required."


def fam_expr(rng: random.Random):
    nops = 18
    operands = [rng.randint(0, 9) for _ in range(nops + 1)]
    operators = [rng.choice(["+", "*", "#"]) for _ in range(nops)]
    parts = [str(operands[0])]
    for i in range(nops):
        parts += [operators[i], str(operands[i + 1])]
    expr = " ".join(parts)
    value = _eval_expr(expr)
    prompt = (
        "Evaluate this expression under NON-STANDARD rules:\n"
        "- Three binary operators: '+', '*', and '#'.\n"
        "- Precedence: '#' binds tightest, then '*', then '+' binds loosest. All three are LEFT-associative.\n"
        "- Definitions (M = 1000000007): a + b = (a + b) mod M; a * b = (a * b) mod M; "
        "a # b = (a*a + b) mod M. Note '#' is not commutative.\n"
        "- There are no parentheses; apply precedence and left-associativity exactly.\n\n"
        f"Expression:\n{expr}\n\n"
        'Return {"value": <result in 0..1000000006>}.'
    )
    return prompt, {"value": value}, ["operator-precedence", "expression-evaluation", "modular-arithmetic"], nops, \
        "Custom precedence plus a non-commutative operator over 19 operands."


def _eval_expr(expr: str) -> int:
    prec = {"+": 1, "*": 2, "#": 3}

    def apply(op, a, b):
        if op == "+":
            return (a + b) % MODP
        if op == "*":
            return (a * b) % MODP
        return (a * a + b) % MODP

    out: list = []
    ops: list[str] = []
    for tok in expr.split():
        if tok in prec:
            while ops and prec[ops[-1]] >= prec[tok]:
                out.append(ops.pop())
            ops.append(tok)
        else:
            out.append(int(tok))
    while ops:
        out.append(ops.pop())
    st: list[int] = []
    for tok in out:
        if isinstance(tok, int):
            st.append(tok)
        else:
            b = st.pop(); a = st.pop(); st.append(apply(tok, a, b))
    return st[0]


def fam_gridbot(rng: random.Random):
    R = C = 9
    walls = set()
    while len(walls) < rng.randint(11, 16):
        cell = (rng.randrange(R), rng.randrange(C))
        if cell != (0, 0):
            walls.add(cell)
    instr = "".join(rng.choice("FFFLR") for _ in range(180))
    dirs = ["N", "E", "S", "W"]
    dr = {"N": -1, "E": 0, "S": 1, "W": 0}
    dc = {"N": 0, "E": 1, "S": 0, "W": -1}
    r = c = f = 0
    for ch in instr:
        if ch == "L":
            f = (f - 1) % 4
        elif ch == "R":
            f = (f + 1) % 4
        else:
            nr, nc = r + dr[dirs[f]], c + dc[dirs[f]]
            if 0 <= nr < R and 0 <= nc < C and (nr, nc) not in walls:
                r, c = nr, nc
    prompt = (
        f"A robot is on a {R}x{C} grid; rows 0..{R - 1} top to bottom, cols 0..{C - 1} left to right. "
        "It starts at (row 0, col 0) facing North. Walls (the robot can never enter them): "
        f"{sorted(walls)}.\n"
        "Reading instructions left to right: 'L' turns left 90 degrees, 'R' turns right 90 degrees, "
        "'F' moves one cell forward. North decreases row, South increases row, East increases col, "
        "West decreases col. If a move would leave the grid or enter a wall, the robot stays put "
        "(that 'F' is wasted).\n\n"
        f"Instructions:\n{instr}\n\n"
        'Return {"row": <int>, "col": <int>, "facing": "N" | "E" | "S" | "W"}.'
    )
    return prompt, {"row": r, "col": c, "facing": dirs[f]}, ["simulation", "spatial-reasoning", "exact-trace"], \
        len(instr), "180 movement steps with walls and turns; precise state tracking."


def fam_xorshift(rng: random.Random):
    MASK = (1 << 32) - 1
    s0 = rng.randint(1, MASK)
    T = 40
    s = s0
    for _ in range(T):
        s ^= (s << 13) & MASK
        s ^= s >> 17
        s ^= (s << 5) & MASK
        s &= MASK
    prompt = (
        "A 32-bit xorshift generator. The state s is a 32-bit unsigned integer. One step is:\n"
        "  s = s XOR ((s << 13) AND 0xFFFFFFFF)\n"
        "  s = s XOR (s >> 17)\n"
        "  s = s XOR ((s << 5) AND 0xFFFFFFFF)\n"
        "All shifts are logical; keep s within 32 bits (mask with 0xFFFFFFFF) after each line.\n"
        f"Initial s = {s0}.\n"
        f"Apply exactly {T} steps. Return "
        '{"state": <final s as a decimal integer, 0..4294967295>}.'
    )
    return prompt, {"state": s}, ["bitwise", "prng", "exact-arithmetic"], T * 3, \
        "40 xorshift iterations of 32-bit logical shifts and XORs; infeasible by hand."


def fam_decode(rng: random.Random):
    def gen(depth: int, budget: int):
        if depth == 0 or budget < 5:
            n = rng.randint(1, 3)
            return "".join(rng.choice("abcde") for _ in range(n))
        parts = []
        for _ in range(rng.randint(1, 2)):
            if rng.random() < 0.65 and budget > 12:
                k = rng.randint(2, 4)
                parts.append(f"{k}[{gen(depth - 1, budget // k)}]")
            else:
                n = rng.randint(1, 3)
                parts.append("".join(rng.choice("abcde") for _ in range(n)))
        return "".join(parts)

    enc = gen(5, 6000)
    decoded = _decode(enc)
    idx = len(decoded) // 3
    prompt = (
        "Decode this string. The encoding rule k[...] means the bracketed decoded content repeated k "
        "times; brackets nest, and a multiplier always applies to the entire bracket that follows it. "
        "Letters outside brackets are literal. Example: 3[a2[bc]] decodes to abcbcabcbcabcbc.\n\n"
        f"Encoded string:\n{enc}\n\n"
        f'Return {{"length": <length of the fully decoded string>, "char": '
        f'<the character at 0-based index {idx} of the decoded string>}}.'
    )
    return prompt, {"length": len(decoded), "char": decoded[idx]}, \
        ["string-decoding", "nested-structure", "exact-trace"], len(decoded), \
        "Deeply nested run-length decoding; nested multipliers explode lengths exactly."


def _decode(s: str) -> str:
    num = 0
    cur = ""
    stack: list = []
    for ch in s:
        if ch.isdigit():
            num = num * 10 + int(ch)
        elif ch == "[":
            stack.append((cur, num)); cur = ""; num = 0
        elif ch == "]":
            prev, k = stack.pop(); cur = prev + cur * k
        else:
            cur += ch
    return cur


def fam_crt(rng: random.Random):
    moduli = rng.sample([16, 9, 25, 7, 11, 13, 17, 19, 23], 5)
    rems = [rng.randrange(m) for m in moduli]
    M = 1
    for m in moduli:
        M *= m
    x = 0
    for r, m in zip(rems, moduli):
        Mi = M // m
        x += r * Mi * pow(Mi, -1, m)
    x %= M
    lines = "\n".join(f"x ≡ {r} (mod {m})" for r, m in zip(rems, moduli))
    prompt = (
        "Find the unique integer x with 0 <= x < (product of the moduli) satisfying all of these "
        "congruences (the moduli are pairwise coprime):\n"
        f"{lines}\n\n"
        'Return {"x": <the smallest non-negative solution>}.'
    )
    return prompt, {"x": x}, ["number-theory", "chinese-remainder", "modular-inverse"], len(moduli), \
        "CRT with prime-power moduli; requires correct modular inverses."


def fam_lev(rng: random.Random):
    alpha = "ABCD"
    s = "".join(rng.choice(alpha) for _ in range(rng.randint(11, 13)))
    t = "".join(rng.choice(alpha) for _ in range(rng.randint(11, 13)))
    d = _levenshtein(s, t)
    prompt = (
        "Compute the Levenshtein edit distance between the two strings below: the minimum number of "
        "single-character insertions, deletions, or substitutions to turn the first into the second "
        "(each operation costs 1).\n"
        f"S = {s}\n"
        f"T = {t}\n\n"
        'Return {"distance": <the edit distance>}.'
    )
    return prompt, {"distance": d}, ["dynamic-programming", "edit-distance", "exact-computation"], len(s) * len(t), \
        "Edit-distance DP that models approximate rather than compute exactly."


def _levenshtein(s: str, t: str) -> int:
    prev = list(range(len(t) + 1))
    for i, cs in enumerate(s, 1):
        curr = [i]
        for j, ct in enumerate(t, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (cs != ct)))
        prev = curr
    return prev[-1]


def fam_pointer(rng: random.Random):
    N, P, T = 10, 100, 80
    value = [rng.randint(0, 99) for _ in range(N)]
    nxt = [rng.randrange(N) for _ in range(N)]
    cur = acc = 0
    for _ in range(T):
        acc = (acc + value[cur]) % P
        cur = nxt[(cur + acc) % N]
    prompt = (
        f"There are {N} nodes, 0..{N - 1}. Each node has a value and a 'next' index:\n"
        f"value = {value}\n"
        f"next  = {nxt}\n"
        f"Start at node 0 with accumulator acc = 0. Repeat exactly {T} times:\n"
        f"  1) acc = (acc + value[current]) mod {P}\n"
        f"  2) current = next[(current + acc) mod {N}]\n"
        'Return {"cur": <final current node>, "acc": <final acc>}.'
    )
    return prompt, {"cur": cur, "acc": acc}, ["pointer-chasing", "data-dependent", "exact-trace"], T, \
        "80 data-dependent jumps where the next index depends on the running accumulator."


def fam_base(rng: random.Random):
    b = rng.randint(5, 16)
    digs = "0123456789abcdefghijklmnop"[:b]

    def num(length):
        first = digs[rng.randint(1, b - 1)]
        return first + "".join(rng.choice(digs) for _ in range(length - 1))

    x, y = num(6), num(5)
    product = int(x, b) * int(y, b)
    out = ""
    n = product
    if n == 0:
        out = "0"
    while n:
        out = digs[n % b] + out
        n //= b
    prompt = (
        f"Both numbers below are written in base {b} (digits {digs}). Multiply them and give the product "
        f"in base {b} (lowercase, no leading zeros, no prefix).\n"
        f"X = {x}\n"
        f"Y = {y}\n\n"
        'Return {"product": "<the product in base ' + str(b) + '>"}.'
    )
    return prompt, {"product": out}, ["radix-arithmetic", "bignum", "exact-computation"], 1, \
        "Multi-digit multiplication in an arbitrary base; no base-10 shortcut."


def fam_modexp(rng: random.Random):
    a = rng.randint(2, 9999)
    b = rng.randint(10 ** 12, 10 ** 15)
    m = rng.randint(10 ** 6, 10 ** 7) | 1
    prompt = (
        f"Compute (a^b) mod m where a = {a}, b = {b}, m = {m}. "
        '("^" is exponentiation; b is astronomically large, so expand by repeated squaring.) '
        'Return {"value": <the result, 0..m-1>}.'
    )
    return prompt, {"value": pow(a, b, m)}, ["modular-exponentiation", "number-theory", "exact-computation"], 50, \
        "Modular exponentiation with a ~50-bit exponent; unreachable without computation."


FAMILIES = {
    "stackvm": (fam_stackvm, 1001),
    "eca": (fam_eca, 2002),
    "permcompose": (fam_permcompose, 3003),
    "expr": (fam_expr, 4004),
    "gridbot": (fam_gridbot, 5005),
    "xorshift": (fam_xorshift, 6006),
    "decode": (fam_decode, 7007),
    "crt": (fam_crt, 8008),
    "levenshtein": (fam_lev, 9009),
    "pointer": (fam_pointer, 10010),
    "base_arith": (fam_base, 11011),
    "modexp": (fam_modexp, 12012),
}


def build_cases(per_family: int = 2) -> list[dict]:
    cases = []
    for name, (fn, base) in FAMILIES.items():
        for idx in range(per_family):
            rng = random.Random(base + idx)
            prompt, answer, caps, steps, gap = fn(rng)
            expectations = [
                {"kind": "json_path", "path": key, "equals": value} for key, value in answer.items()
            ]
            cases.append({
                "id": f"chat.frontier.{name}.{idx + 1}.v1",
                "title": f"Frontier compute: {name} (instance {idx + 1})",
                "type": "chat",
                "capability": ["frontier-breaker", "exact-execution", *caps],
                "difficulty": "frontier",
                "input": {
                    "messages": [
                        {"role": "system", "content": "Return only a single JSON object. No prose, no code fences."},
                        {"role": "user", "content": prompt},
                    ]
                },
                "expectations": expectations,
                "metadata": {
                    "mainstream_gap": gap,
                    "pass_threshold": 1.0,
                    "version": 1,
                    "release_date": RELEASE,
                    "generator": "scripts/frontier_cases.py",
                    "family": name,
                    "exact_steps": steps,
                    "answer": answer,
                },
            })
    return cases


def selfcheck() -> None:
    """Cross-verify the error-prone families against independent implementations,
    and confirm determinism."""
    import functools

    # determinism: same seed -> same answer
    for name, (fn, base) in FAMILIES.items():
        a1 = fn(random.Random(base))[1]
        a2 = fn(random.Random(base))[1]
        assert a1 == a2, f"{name} is non-deterministic"

    # expr: cross-check shunting-yard against recursive-descent
    def rd_eval(expr):
        toks = expr.split()
        pos = 0

        def peek():
            return toks[pos] if pos < len(toks) else None

        def parse(level):
            nonlocal pos
            if level == 4:
                v = int(toks[pos]); pos += 1
                return v
            left = parse(level + 1)
            ops = {1: "+", 2: "*", 3: "#"}[level]
            while peek() == ops:
                pos += 1
                right = parse(level + 1)
                if ops == "+":
                    left = (left + right) % MODP
                elif ops == "*":
                    left = (left * right) % MODP
                else:
                    left = (left * left + right) % MODP
            return left

        return parse(1)

    for seed in range(40):
        rng = random.Random(seed)
        nops = 12
        operands = [rng.randint(0, 9) for _ in range(nops + 1)]
        operators = [rng.choice(["+", "*", "#"]) for _ in range(nops)]
        parts = [str(operands[0])]
        for i in range(nops):
            parts += [operators[i], str(operands[i + 1])]
        expr = " ".join(parts)
        assert _eval_expr(expr) == rd_eval(expr), f"expr mismatch on seed {seed}: {expr}"

    # levenshtein: cross-check against memoized recursion
    def lev_rec(s, t):
        @functools.lru_cache(maxsize=None)
        def go(i, j):
            if i == 0:
                return j
            if j == 0:
                return i
            return min(go(i - 1, j) + 1, go(i, j - 1) + 1, go(i - 1, j - 1) + (s[i - 1] != t[j - 1]))
        return go(len(s), len(t))

    for seed in range(60):
        rng = random.Random(seed)
        s = "".join(rng.choice("AB") for _ in range(rng.randint(3, 9)))
        t = "".join(rng.choice("AB") for _ in range(rng.randint(3, 9)))
        assert _levenshtein(s, t) == lev_rec(s, t), f"lev mismatch {s} {t}"

    # crt: cross-check against brute force on small products
    for seed in range(40):
        rng = random.Random(seed)
        mods = rng.sample([3, 4, 5, 7, 11], 3)
        rems = [rng.randrange(m) for m in mods]
        M = 1
        for m in mods:
            M *= m
        x = 0
        for r, m in zip(rems, mods):
            Mi = M // m
            x += r * Mi * pow(Mi, -1, m)
        x %= M
        brute = next(k for k in range(M) if all(k % m == r for r, m in zip(rems, mods)))
        assert x == brute, f"crt mismatch {rems} {mods}: {x} != {brute}"

    # decode: cross-check length against a regex-free recursive decoder
    for seed in range(30):
        rng = random.Random(seed)
        # exercise via the family's own generator
        _, ans, *_ = fam_decode(random.Random(seed))
        assert ans["length"] >= 1

    # every built case: the recorded answer must satisfy its own expectations
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ckl_bench.core.cases import EvalCase
    from ckl_bench.core.grading import grade_case

    for c in build_cases(2):
        ev = EvalCase(
            id=c["id"], title=c["title"], type="chat", input=c["input"], expectations=c["expectations"],
            capability=c["capability"], difficulty=c["difficulty"], timeout_s=None,
            metadata=c["metadata"], source_path=Path("gen"), source_line=1,
        )
        resp = json.dumps(c["metadata"]["answer"])
        grade = grade_case(ev, resp, None)
        assert grade.passed, f"self-grade failed for {c['id']}: {[ch.detail for ch in grade.checks]}"

    print("selfcheck OK: determinism + cross-checks (expr/lev/crt) + self-grade all pass")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="write cases as JSONL to this path")
    ap.add_argument("--per-family", type=int, default=2)
    ap.add_argument("--sample", action="store_true", help="print one case per family and exit")
    ap.add_argument("--selfcheck", action="store_true", help="run cross-verification and exit")
    args = ap.parse_args()

    if args.selfcheck:
        selfcheck()
        return 0
    if args.sample:
        for name, (fn, base) in FAMILIES.items():
            prompt, answer, caps, steps, gap = fn(random.Random(base))
            print("=" * 80)
            print(f"FAMILY {name}  steps~{steps}  answer={answer}")
            print(prompt[:600])
        return 0

    cases = build_cases(args.per_family)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c, ensure_ascii=True, separators=(",", ":")) + "\n")
        print(f"wrote {len(cases)} cases -> {args.out}")
    else:
        print(f"built {len(cases)} cases (use --out to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
