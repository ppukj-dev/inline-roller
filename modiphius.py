"""Modiphius 2d20 dice logic for the inline roller.

Two roll types live inside the same ``[[ ]]`` inline notation the bot already
uses:

* **Skill Tests** — ``x<count>d20 f<focus> t<target> c<comp>`` e.g. ``2d20f3t12c1``.
  ``f`` and ``c`` are optional and default to ``focus=1`` / ``comp=0``. ``c`` is
  the *complication range* — how many extra faces below 20 also trigger a
  complication: ``c0`` (default) means only a natural 20, ``c1`` means 19-20,
  ``c2`` means 18-20, and so on.
  ``t`` (target number) is required, which is also what distinguishes a
  Modiphius test from a plain ``d20``-library roll like ``[[2d20]]``.
* **Challenge Dice** — ``<count>cd`` e.g. ``6cd`` rolls a pool of d6.

Rolling uses ``random`` directly; the pure evaluation/formatting helpers take
already-rolled dice so they can be unit tested deterministically.
"""

import random
import re

TEST_PREFIX_PATTERN = re.compile(r"^(\d+)d20(.*)$")
TEST_FIELD_PATTERN = re.compile(r"([ftc])(\d+)")
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
    """Return test params dict, or None if ``expr`` is not a Modiphius test.

    The ``f`` (focus), ``t`` (target) and ``c`` (complication range) fields
    may appear in any order; ``t`` is required, ``f`` defaults to 1 and ``c``
    to 0. The returned ``comp`` is the complication *threshold* (a die at or
    above it is a complication), derived as ``20 - c`` so ``c0`` yields 20,
    ``c1`` yields 19, and so on. Duplicate fields or trailing junk are
    rejected.
    """
    prefix = TEST_PREFIX_PATTERN.match(expr.strip())
    if prefix is None:
        return None
    count = int(prefix.group(1))
    rest = prefix.group(2)

    fields = {}
    pos = 0
    for field in TEST_FIELD_PATTERN.finditer(rest):
        if field.start() != pos:  # gap or unexpected character
            return None
        letter = field.group(1)
        if letter in fields:  # duplicate field
            return None
        fields[letter] = int(field.group(2))
        pos = field.end()
    if pos != len(rest):  # trailing junk after the last field
        return None
    if "t" not in fields:  # target number is mandatory
        return None

    return {
        "count": count,
        "focus": fields.get("f", 1),
        "target": fields["t"],
        "comp": 20 - fields.get("c", 0),
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


def _test_decode(count: int, focus: int, target: int, comp: int) -> str:
    """Human-readable breakdown of a test command's parameters."""
    return f"{count}d20 · Focus {focus} · TN {target} · Comp {comp}+"


def format_test_full(command: str, dice, focus: int, target: int, comp: int,
                     successes: int, complications: int) -> str:
    """Full result block for the dump channel (the non-inline reference).

    Includes the raw command and a decoded breakdown so the roll can be
    referenced later, since the inline 【 】 view only shows the outcome.
    """
    ref = f"🎲 Rolling `{command}` · {_test_decode(len(dice), focus, target, comp)}"
    dice_line = f"Dice: [{_dice_str(dice)}]"
    if successes > 0 and complications > 0:
        body = f"✨ {_successes(successes)} | ⚠️ {_complications(complications)}"
    elif successes > 0:
        body = f"✨ {_successes(successes)}"
    elif complications > 0:
        body = f"💥 [Failure] | ⚠️ {_complications(complications)}"
    else:
        body = "💥 [Failure]"
    return f"{ref}\n{dice_line}\n{body}"


def format_test_inline(successes: int, complications: int) -> str:
    """Compact 【 】 replacement shown inline in the proxied message."""
    if successes > 0 and complications > 0:
        return f"【 ✨{successes} ⚠️{complications} 】"
    if successes > 0:
        return f"【 ✨{successes} 】"
    if complications > 0:
        return f"【 💥 ⚠️{complications} 】"
    return "【 💥 】"


def format_challenge_full(command: str, dice, result: int,
                          effects: int) -> str:
    ref = f"🎲 Rolling `{command}` · {len(dice)} Challenge Dice"
    dice_line = f"Dice: [{_dice_str(dice)}]"
    totals = f"**Total Result:** {result} | **Total Effects:** {effects}"
    return f"{ref}\n{dice_line}\n{totals}"


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
    command = expr.strip()
    test = parse_test(expr)
    if test is not None:
        dice = [random.randint(1, 20) for _ in range(test["count"])]
        successes, complications = evaluate_test(
            dice, test["focus"], test["target"], test["comp"]
        )
        return {
            "full_text": format_test_full(
                command, dice, test["focus"], test["target"], test["comp"],
                successes, complications
            ),
            "inline": format_test_inline(successes, complications),
            "summary": _test_summary(successes, complications),
            "expression": str(dice),
        }

    challenge = parse_challenge(expr)
    if challenge is not None:
        dice = [random.randint(1, 6) for _ in range(challenge["count"])]
        result, effects = evaluate_challenge(dice)
        return {
            "full_text": format_challenge_full(command, dice, result, effects),
            "inline": format_challenge_inline(result, effects),
            "summary": f"{result} Result | {effects} Effects",
            "expression": str(dice),
        }

    return None
