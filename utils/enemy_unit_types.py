"""
utils/enemy_unit_types.py
─────────────────────────
Stat presets for enemy unit types, plus the helper that generates
final stats for any spawn (GM manual, GM bulk, or auto-spawn).

Priority order when generating stats
─────────────────────────────────────
1. GM override  – if the GM explicitly sets a stat (e.g. speed=25) it is used
                  as the base, still subject to the natural variance roll.
2. Type preset  – the unit_type label is matched (case-insensitive, substring)
                  against the PRESETS table to find the base stats.
3. Unknown type – if no preset matches, wide random variance is applied so
                  unrecognised types feel genuinely unpredictable (Option C).

Variance
─────────
Each preset defines a variance range (lo, hi) applied per-stat.
Known types:  ±3  (tight, flavourful)
Unknown types: -8 to +15 (wide, chaotic — Option C)
"""

from __future__ import annotations
import random
from typing import Optional

# ── Stat bundle dataclass ──────────────────────────────────────────────────────

class EnemyStats:
    __slots__ = ("attack", "defense", "speed", "morale", "supply", "recon")

    def __init__(self, attack, defense, speed, morale, supply, recon):
        self.attack  = max(1, attack)
        self.defense = max(1, defense)
        self.speed   = max(1, speed)
        self.morale  = max(1, morale)
        self.supply  = max(1, supply)
        self.recon   = max(1, recon)

    def as_tuple(self):
        return (self.attack, self.defense, self.speed,
                self.morale, self.supply, self.recon)

    def summary(self) -> str:
        """Short human-readable stat line for confirmation messages."""
        hexes = max(1, self.speed // 10)
        return (
            f"ATK {self.attack} | DEF {self.defense} | SPD {self.speed} "
            f"({hexes} hex/turn) | MOR {self.morale} | SUP {self.supply} | REC {self.recon}"
        )


# ── Preset table ───────────────────────────────────────────────────────────────
# Each entry: keywords (list of substrings to match), base stats dict,
# variance (lo, hi) applied independently to every stat.
#
# speed → hexes/turn mapping (from turn_engine):
#   1–9   → 1 hex   20–29 → 2 hexes
#   10–19 → 1 hex   30+   → 3 hexes

_PRESETS: list[dict] = [
    # ── Fast movers ────────────────────────────────────────────────────────────
    {
        "keywords": ["cavalry", "raider", "bike", "hover", "fast"],
        "base": dict(attack=12, defense=7,  speed=30, morale=10, supply=8,  recon=14),
        "variance": (-3, 5),   # speed stays 27-35 → always 3 hexes/turn
        "label": "Cavalry/Raider",
    },
    {
        "keywords": ["scout", "recon", "ranger", "skirmish"],
        "base": dict(attack=8,  defense=7,  speed=20, morale=9,  supply=10, recon=18),
        "variance": (-3, 4),   # speed stays 17-24 → 1-2 hexes/turn
        "label": "Scout/Recon",
    },
    # ── Standard infantry ──────────────────────────────────────────────────────
    {
        "keywords": ["infantry", "grunt", "soldier", "trooper", "militia", "line"],
        "base": dict(attack=11, defense=11, speed=10, morale=11, supply=11, recon=9),
        "variance": (-3, 3),
        "label": "Infantry",
    },
    {
        "keywords": ["marine", "shock", "assault", "breacher"],
        "base": dict(attack=15, defense=9,  speed=12, morale=14, supply=9,  recon=10),
        "variance": (-3, 3),
        "label": "Marines/Shock",
    },
    # ── Heavy / armoured ──────────────────────────────────────────────────────
    {
        "keywords": ["heavy", "tank", "armour", "armor", "mech", "walker"],
        "base": dict(attack=18, defense=18, speed=8,  morale=13, supply=10, recon=6),
        "variance": (-3, 3),   # speed stays 5-11 → 0-1 hex/turn
        "label": "Heavy/Tank",
    },
    {
        "keywords": ["fortress", "bastion", "bunker", "dug"],
        "base": dict(attack=14, defense=22, speed=4,  morale=16, supply=12, recon=5),
        "variance": (-2, 2),
        "label": "Fortress",
    },
    # ── Artillery / ranged ─────────────────────────────────────────────────────
    {
        "keywords": ["artillery", "siege", "mortar", "cannon", "howitzer"],
        "base": dict(attack=22, defense=6,  speed=5,  morale=8,  supply=8,  recon=7),
        "variance": (-3, 3),
        "label": "Artillery/Siege",
    },
    {
        "keywords": ["sniper", "marksman", "ranger"],
        "base": dict(attack=18, defense=6,  speed=12, morale=10, supply=9,  recon=16),
        "variance": (-3, 3),
        "label": "Sniper",
    },
    # ── Support ────────────────────────────────────────────────────────────────
    {
        "keywords": ["support", "medic", "engineer", "logistics", "supply"],
        "base": dict(attack=7,  defense=9,  speed=10, morale=14, supply=18, recon=11),
        "variance": (-3, 3),
        "label": "Support/Medic",
    },
    # ── Elite ──────────────────────────────────────────────────────────────────
    {
        "keywords": ["elite", "veteran", "commando", "spec", "special", "shadow"],
        "base": dict(attack=16, defense=14, speed=20, morale=16, supply=12, recon=15),
        "variance": (-3, 4),   # speed 17-24 → 1-2 hexes/turn
        "label": "Elite",
    },
    # ── Drone / autonomous ─────────────────────────────────────────────────────
    {
        "keywords": ["drone", "bot", "automaton", "robot", "mech"],
        "base": dict(attack=13, defense=10, speed=15, morale=20, supply=6,  recon=14),
        "variance": (-3, 3),
        "label": "Drone/Bot",
    },
    # ── Horror / alien ────────────────────────────────────────────────────────
    {
        "keywords": ["beast", "alien", "creature", "horror", "swarm", "hive", "xeno"],
        "base": dict(attack=14, defense=8,  speed=22, morale=20, supply=20, recon=10),
        "variance": (-4, 6),   # speed 18-28 → 1-2 hexes/turn
        "label": "Beast/Alien",
    },
]

# Flat keyword → preset lookup built once at import
_KEYWORD_MAP: dict[str, dict] = {}
for _p in _PRESETS:
    for _kw in _p["keywords"]:
        _KEYWORD_MAP[_kw] = _p


# ── Public API ─────────────────────────────────────────────────────────────────

def resolve_preset(unit_type: str) -> Optional[dict]:
    """Return the matching preset dict for a unit_type label, or None."""
    needle = unit_type.lower()
    # Exact keyword match first
    if needle in _KEYWORD_MAP:
        return _KEYWORD_MAP[needle]
    # Substring match
    for kw, preset in _KEYWORD_MAP.items():
        if kw in needle:
            return preset
    return None


def generate_stats(
    unit_type: str,
    *,
    override_attack:  Optional[int] = None,
    override_defense: Optional[int] = None,
    override_speed:   Optional[int] = None,
    override_morale:  Optional[int] = None,
    override_supply:  Optional[int] = None,
    override_recon:   Optional[int] = None,
) -> EnemyStats:
    """
    Generate final stats for a new enemy unit.

    Resolution order per stat:
      1. GM override (if provided) — used as the base, variance still applied
      2. Type preset base value
      3. Unknown-type fallback (base=10, wide variance)
    """
    preset = resolve_preset(unit_type)

    if preset:
        base     = preset["base"]
        lo, hi   = preset["variance"]
    else:
        # Option C: unknown types get wide random variance
        base     = dict(attack=10, defense=10, speed=10,
                        morale=10, supply=10,  recon=10)
        lo, hi   = -8, 15

    def _stat(name: str, override: Optional[int]) -> int:
        b = override if override is not None else base[name]
        return b + random.randint(lo, hi)

    return EnemyStats(
        attack  = _stat("attack",  override_attack),
        defense = _stat("defense", override_defense),
        speed   = _stat("speed",   override_speed),
        morale  = _stat("morale",  override_morale),
        supply  = _stat("supply",  override_supply),
        recon   = _stat("recon",   override_recon),
    )


def preset_summary_table() -> str:
    """
    Return a compact Markdown table of all known presets for GM reference.
    Shown in the spawn modal confirmation or a /help command.
    """
    header = (
        "**Known unit type presets** (unrecognised types get wide random stats)\n"
        "```\n"
        f"{'Type':<18} {'ATK':>4} {'DEF':>4} {'SPD':>4} {'MOR':>4} {'SUP':>4} {'REC':>4}  Hexes/turn\n"
        + "─" * 65 + "\n"
    )
    rows = []
    seen = set()
    for p in _PRESETS:
        lbl = p["label"]
        if lbl in seen:
            continue
        seen.add(lbl)
        b = p["base"]
        hexes = max(1, b["speed"] // 10)
        rows.append(
            f"{lbl:<18} {b['attack']:>4} {b['defense']:>4} {b['speed']:>4} "
            f"{b['morale']:>4} {b['supply']:>4} {b['recon']:>4}  {hexes}"
        )
    return header + "\n".join(rows) + "\n```"