"""Cryptographically secure dice. The ONLY source of randomness in the game.

Every roll made through the engine is recorded in the campaign's hash-chained event log with
its individual die faces, so any result can be audited later and none can be quietly redone.
"""
import re
import secrets

TERM = re.compile(r"([+-]?)(?:(\d*)d(\d+)(?:(kh|kl)(\d+))?|(\d+))", re.I)
MAX_DICE = 200


class DiceError(ValueError):
    pass


def d(sides):
    return secrets.randbelow(sides) + 1


def roll(expr, mode=None, crit=False):
    """Roll an expression like '1d20+5', '2d6+1d4-1', '4d6kh3'.

    mode: 'adv' / 'dis' applies to a single d20 term (rolls 2, keeps high/low).
    crit: double the number of dice (critical hit damage), modifiers unchanged.
    Returns a dict with total, per-term faces, natural d20 (if any) and display text.
    """
    e = str(expr).replace(" ", "").lower()
    if not e or TERM.sub("", e):
        raise DiceError(f"can't parse dice expression '{expr}'")
    total, terms, nat, text = 0, [], None, []
    for sign, n, sides, keep, k, flat in TERM.findall(e):
        mult = -1 if sign == "-" else 1
        if flat:
            total += mult * int(flat)
            terms.append({"flat": mult * int(flat)})
            text.append(f"{sign or '+'}{flat}")
            continue
        n, sides = int(n or 1), int(sides)
        if sides < 2 or n < 1 or n > MAX_DICE:
            raise DiceError(f"bad dice term {n}d{sides}")
        if crit:
            n *= 2
        if sides == 20 and n == 1 and mode in ("adv", "dis"):
            a, b = d(20), d(20)
            kept = max(a, b) if mode == "adv" else min(a, b)
            nat = kept
            total += mult * kept
            terms.append({"dice": f"1d20", "faces": [a, b], "kept": [kept], "mode": mode})
            text.append(f"{sign or '+'}d20({mode} {a},{b}→{kept})")
            continue
        faces = [d(sides) for _ in range(n)]
        kept = faces
        if keep:
            kept = sorted(faces, reverse=(keep == "kh"))[: int(k)]
        if sides == 20 and n == 1:
            nat = faces[0]
        total += mult * sum(kept)
        terms.append({"dice": f"{n}d{sides}", "faces": faces, "kept": kept, "sign": mult})
        shown = ",".join(map(str, faces)) + (f"→{','.join(map(str, kept))}" if keep else "")
        text.append(f"{sign or '+'}{n}d{sides}({shown})")
    return {"expr": str(expr), "mode": mode, "crit": crit, "total": total, "nat": nat, "terms": terms,
            "text": " ".join(text).lstrip("+") + f" = {total}"}


def d20(mod=0, mode=None):
    """A d20 test. mode may be 'adv', 'dis' or None (both cancel out before calling)."""
    expr = "1d20" + (f"{mod:+d}" if mod else "")
    return roll(expr, mode)


def combine_modes(adv_sources, dis_sources):
    """SRD: any Advantage and any Disadvantage cancel; multiple of one kind don't stack."""
    if adv_sources and dis_sources:
        return None
    if adv_sources:
        return "adv"
    if dis_sources:
        return "dis"
    return None


def average(expr):
    e = str(expr).replace(" ", "").lower()
    total = 0.0
    for sign, n, sides, keep, k, flat in TERM.findall(e):
        mult = -1 if sign == "-" else 1
        if flat:
            total += mult * int(flat)
        else:
            total += mult * int(n or 1) * (int(sides) + 1) / 2
    return int(total)
