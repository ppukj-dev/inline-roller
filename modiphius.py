"""Modiphius 2d20 dice logic for the inline roller.

Two roll types live inside the same ``[[ ]]`` inline notation the bot already
uses:

* **Skill Tests** — ``x<count>d20 f<focus> t<target> c<comp>`` e.g. ``2d20f3t12c19``.
  ``f`` and ``c`` are optional and default to ``focus=1`` / ``comp=20``.
  ``t`` (target number) is required, which is also what distinguishes a
  Modiphius test from a plain ``d20``-library roll like ``[[2d20]]``.
* **Challenge Dice** — ``<count>cd`` e.g. ``6cd`` rolls a pool of d6.

Rolling uses ``random`` directly; the pure evaluation/formatting helpers take
already-rolled dice so they can be unit tested deterministically.
"""

import random
import re

TEST_PATTERN = re.compile(r"^(\d+)d20(?:f(\d+))?t(\d+)(?:c(\d+))?$")
CHALLENGE_PATTERN = re.compile(r"^(\d+)cd$")

# d6 face -> (result, effect) for Challenge Dice.
CHALLENGE_FACES = {
    1: (1, 0),
    2: (2, 0),
    3: (0, 0),
    4: (0, 0),
    5: (1, 1),
    6: (1, 1),
}


def parse_test(expr: str):
    """Return test params dict, or None if ``expr`` is not a Modiphius test."""
    match = TEST_PATTERN.match(expr.strip())
    if match is None:
        return None
    return {
        "count": int(match.group(1)),
        "focus": int(match.group(2)) if match.group(2) else 1,
        "target": int(match.group(3)),
        "comp": int(match.group(4)) if match.group(4) else 20,
    }


def parse_challenge(expr: str):
    """Return challenge params dict, or None if ``expr`` is not challenge dice."""
    match = CHALLENGE_PATTERN.match(expr.strip())
    if match is None:
        return None
    return {"count": int(match.group(1))}


def is_modiphius(expr: str) -> bool:
    return parse_test(expr) is not None or parse_challenge(expr) is not None


def evaluate_test(dice, focus: int, target: int, comp: int):
    """Count (successes, complications) for already-rolled d20 ``dice``."""
    successes = 0
    complications = 0
    for die in dice:
        if die <= target:
            successes += 1
        if die <= focus:
            successes += 1
        if die >= comp:
            complications += 1
    return successes, complications


def evaluate_challenge(dice):
    """Sum (total_result, total_effects) for already-rolled d6 ``dice``."""
    result = 0
    effects = 0
    for die in dice:
        die_result, die_effect = CHALLENGE_FACES[die]
        result += die_result
        effects += die_effect
    return result, effects


def _successes(n: int) -> str:
    return f"{n} Success" if n == 1 else f"{n} Successes"


def _complications(n: int) -> str:
    return f"{n} Complication" if n == 1 else f"{n} Complications"


def _dice_str(dice) -> str:
    return ", ".join(str(d) for d in dice)


def format_test_full(dice, successes: int, complications: int) -> str:
    """Full result line for the dump channel."""
    header = f"🎲 Rolling {len(dice)}d20: [{_dice_str(dice)}]"
    if successes > 0 and complications > 0:
        body = f"✨ {_successes(successes)} | ⚠️ {_complications(complications)}"
    elif successes > 0:
        body = f"✨ {_successes(successes)}"
    elif complications > 0:
        body = f"💥 [Failure] | ⚠️ {_complications(complications)}"
    else:
        body = "💥 [Failure]"
    return f"{header}\n{body}"


def format_test_inline(successes: int, complications: int) -> str:
    """Compact 【 】 replacement shown inline in the proxied message."""
    if successes > 0 and complications > 0:
        return f"【 ✨{successes} ⚠️{complications} 】"
    if successes > 0:
        return f"【 ✨{successes} 】"
    if complications > 0:
        return f"【 💥 ⚠️{complications} 】"
    return "【 💥 】"


def format_challenge_full(dice, result: int, effects: int) -> str:
    header = f"🎲 Rolling {len(dice)}d6: [{_dice_str(dice)}]"
    return f"{header}\n**Total Result:** {result} | **Total Effects:** {effects}"


def format_challenge_inline(result: int, effects: int) -> str:
    return f"【 🎯{result} ⚡{effects} 】"


def _test_summary(successes: int, complications: int) -> str:
    """One-line summary stored in the roll history table."""
    part = _successes(successes) if successes > 0 else "Failure"
    if complications > 0:
        return f"{part} | {_complications(complications)}"
    return part


def roll(expr: str):
    """Roll a Modiphius test or challenge pool.

    Returns a dict with ``full_text`` (dump channel), ``inline`` (【 】
    replacement), ``summary`` and ``expression`` (both for history), or
    ``None`` if ``expr`` is not Modiphius syntax and should fall through to
    the existing d20 path.
    """
    test = parse_test(expr)
    if test is not None:
        dice = [random.randint(1, 20) for _ in range(test["count"])]
        successes, complications = evaluate_test(
            dice, test["focus"], test["target"], test["comp"]
        )
        return {
            "full_text": format_test_full(dice, successes, complications),
            "inline": format_test_inline(successes, complications),
            "summary": _test_summary(successes, complications),
            "expression": str(dice),
        }

    challenge = parse_challenge(expr)
    if challenge is not None:
        dice = [random.randint(1, 6) for _ in range(challenge["count"])]
        result, effects = evaluate_challenge(dice)
        return {
            "full_text": format_challenge_full(dice, result, effects),
            "inline": format_challenge_inline(result, effects),
            "summary": f"{result} Result | {effects} Effects",
            "expression": str(dice),
        }

    return None
