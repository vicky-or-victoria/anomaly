"""
Warbot unit progression registry.

This module keeps veterancy, XP rewards, and evolution definitions out of the
combat resolver so brigade identity stays data-driven and easy to extend.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional

from utils.brigades import get_brigade


STAT_KEYS = ("attack", "defense", "speed", "morale", "supply", "recon")

VETERANCY_ORDER = ["Green", "Hardened", "Veteran", "Elite", "Legendary"]
VETERANCY_THRESHOLDS = {
    "Green": 0,
    "Hardened": 175,
    "Veteran": 450,
    "Elite": 900,
    "Legendary": 1600,
}

VETERANCY_BONUSES = {
    "Green": {},
    "Hardened": {"attack": 1, "defense": 1, "morale": 1},
    "Veteran": {"attack": 2, "defense": 2, "morale": 2, "recon": 1},
    "Elite": {"attack": 4, "defense": 3, "morale": 3, "recon": 2, "speed": 1},
    "Legendary": {"attack": 6, "defense": 5, "morale": 4, "recon": 3, "speed": 1, "supply": 2},
}

FAMILY_CONFIG = {
    "infantry": {
        "family": "Infantry Brigade",
        "base_unit": "Line Infantry Squad",
        "capstone": "Hold the Line",
        "tier_notes": {
            "Hardened": "Dig In improves to +5 defense.",
            "Veteran": "Dug-in first contact gains morale resistance.",
            "Elite": "Dig In improves to +6; first defense after movement gains +2 defense roll.",
            "Legendary": "Hold the Line: current-hex defense gains +2 attack roll and nearby Infantry gain morale support.",
        },
    },
    "armoured": {
        "family": "Armoured Brigade",
        "base_unit": "Motorized Armoured Squad",
        "capstone": "Breakthrough",
        "family_stat_bonuses": {
            "Hardened": {"supply": 1},
            "Veteran": {"attack": 1, "defense": 1, "speed": 1},
        },
        "tier_notes": {
            "Hardened": "+1 Supply and heavier survivability profile.",
            "Veteran": "+1 Attack, +1 Defense, +1 Speed.",
            "Elite": "Stationary launch attacks gain +2 attack roll.",
            "Legendary": "Breakthrough: wins prime the next attack for +3 attack roll.",
        },
    },
    "aerial": {
        "family": "Aerial Brigade",
        "base_unit": "Air Assault Squad",
        "capstone": "Sky Hunter",
        "family_stat_bonuses": {
            "Hardened": {"recon": 2, "speed": 1},
            "Elite": {"defense": 1},
        },
        "tier_notes": {
            "Hardened": "+2 Recon, +1 Speed.",
            "Veteran": "First recon sweep each turn has improved battlefield effect.",
            "Elite": "+1 Defense; first combat after movement gains +2 attack roll.",
            "Legendary": "Sky Hunter: attacking revealed targets gains +2 attack roll.",
        },
    },
    "ranger": {
        "family": "Ranger Brigade",
        "base_unit": "Ranger Squad",
        "capstone": "Ghost Trail",
        "family_stat_bonuses": {
            "Hardened": {"recon": 2},
            "Elite": {"recon": 1, "speed": 1},
        },
        "tier_notes": {
            "Hardened": "+2 Recon; scavenge bonus improves from +3 to +4.",
            "Veteran": "First scavenge each turn restores +1 Morale.",
            "Elite": "+3 total Recon and +1 Speed.",
            "Legendary": "Ghost Trail: recently spotted enemies suffer +2 attack roll pressure.",
        },
    },
    "artillery": {
        "family": "Artillery Brigade",
        "base_unit": "Field Battery",
        "capstone": "Fire Mission",
        "tier_notes": {
            "Hardened": "Armed attacks gain +1 effectiveness.",
            "Veteran": "Armed state gives +2 attack roll; stationary adds +1 attack.",
            "Elite": "Splash becomes more dangerous and efficient.",
            "Legendary": "Fire Mission: armed attacks gain enhanced splash pressure.",
        },
    },
    "engineering": {
        "family": "Engineering Brigade",
        "base_unit": "Combat Engineer Squad",
        "capstone": "Battlefield Grid",
        "family_stat_bonuses": {
            "Veteran": {"defense": 1},
        },
        "tier_notes": {
            "Hardened": "Repair efficiency improves.",
            "Veteran": "Repair Adjacent strengthens; +1 Defense.",
            "Elite": "Fortify and support actions become more efficient.",
            "Legendary": "Battlefield Grid: adjacent friendlies gain sustain or minor defense support.",
        },
    },
    "special_ops": {
        "family": "Special Operations Brigade",
        "base_unit": "Special Operations Team",
        "capstone": "Decapitation Strike",
        "family_stat_bonuses": {
            "Hardened": {"recon": 1, "morale": 1},
            "Veteran": {"attack": 1, "recon": 1},
            "Elite": {"speed": 1, "attack": 2},
        },
        "tier_notes": {
            "Hardened": "+1 Recon, +1 Morale.",
            "Veteran": "+1 Attack, +1 Recon.",
            "Elite": "+1 Speed, +2 Attack.",
            "Legendary": "Decapitation Strike: first combat after insertion/recon gains +3 attack roll.",
        },
    },
}

DEFAULT_COMBAT_RECORD = {
    "battles_fought": 0,
    "battles_won": 0,
    "kills": 0,
    "defensive_survivals": 0,
    "attacking_wins": 0,
    "recon_successes": 0,
    "armed_attacks": 0,
    "support_actions": 0,
    "fortified_actions": 0,
    "repair_actions": 0,
    "revealed_target_attacks": 0,
    "mobile_attack_wins": 0,
    "heavy_damage_survivals": 0,
    "stationary_armed_wins": 0,
    "splash_multi_hits": 0,
    "last_recon_turn": -1,
    "last_support_turn": -1,
    "last_fortify_turn": -1,
    "last_scavenge_turn": -1,
    "breakthrough_ready": False,
}


def _stats(**kwargs: int) -> Dict[str, int]:
    return {k: v for k, v in kwargs.items() if v}


EVOLUTIONS: Dict[str, Dict[str, Any]] = {
    # Infantry
    "Defensive Infantry Squad": {"family": "infantry", "stage": 1, "parent": None, "branch": "defensive", "xp": 450, "requirements": {"battles_fought": 3, "defensive_survivals": 2}, "bonuses": _stats(defense=1, morale=1), "function": "Stronger static defense."},
    "Assault Infantry Squad": {"family": "infantry", "stage": 1, "parent": None, "branch": "assault", "xp": 450, "requirements": {"battles_fought": 3, "attacking_wins": 2}, "bonuses": _stats(attack=2, morale=1), "function": "Better offensive pressure."},
    "Entrenched Infantry Squad": {"family": "infantry", "stage": 2, "parent": "Defensive Infantry Squad", "branch": "defensive", "xp": 900, "requirements": {"defensive_survivals": 5}, "bonuses": _stats(defense=2, morale=1), "function": "Maximum Dig In efficiency."},
    "Guard Infantry Squad": {"family": "infantry", "stage": 2, "parent": "Defensive Infantry Squad", "branch": "defensive", "xp": 900, "requirements": {"defensive_survivals": 4, "battles_won": 2}, "bonuses": _stats(attack=1, defense=1, morale=2), "function": "Leadership and support aura."},
    "Shock Infantry Squad": {"family": "infantry", "stage": 2, "parent": "Assault Infantry Squad", "branch": "assault", "xp": 900, "requirements": {"kills": 2, "attacking_wins": 2}, "bonuses": _stats(attack=3, morale=1), "function": "Stronger versus fortified positions."},
    "Urban Assault Squad": {"family": "infantry", "stage": 2, "parent": "Assault Infantry Squad", "branch": "assault", "xp": 900, "requirements": {"battles_won": 4, "fortified_actions": 1}, "bonuses": _stats(attack=2, defense=1), "function": "Better close-quarters and static fighting."},

    # Armoured
    "Mechanized Armoured Squad": {"family": "armoured", "stage": 1, "parent": None, "branch": "mechanized", "xp": 450, "requirements": {"battles_won": 3, "heavy_damage_survivals": 1}, "bonuses": _stats(attack=2, defense=2, speed=1), "function": "Better mobile durability."},
    "Breakthrough Armoured Squad": {"family": "armoured", "stage": 1, "parent": None, "branch": "breakthrough", "xp": 450, "requirements": {"battles_won": 3, "kills": 2}, "bonuses": _stats(attack=3, defense=1), "function": "Offensive spearhead."},
    "IFV Armoured Squad": {"family": "armoured", "stage": 2, "parent": "Mechanized Armoured Squad", "branch": "mechanized", "xp": 900, "requirements": {"mobile_attack_wins": 2}, "bonuses": _stats(attack=2, defense=1, speed=1, recon=1), "function": "Combined-arms flexibility."},
    "Heavy Mechanized Squad": {"family": "armoured", "stage": 2, "parent": "Mechanized Armoured Squad", "branch": "mechanized", "xp": 900, "requirements": {"heavy_damage_survivals": 3}, "bonuses": _stats(attack=1, defense=3), "function": "Durable front-line anchor."},
    "Shock Armoured Squad": {"family": "armoured", "stage": 2, "parent": "Breakthrough Armoured Squad", "branch": "breakthrough", "xp": 900, "requirements": {"attacking_wins": 4}, "bonuses": _stats(attack=4, morale=2), "function": "Opening-strike pressure."},
    "Siegebreaker Armoured Squad": {"family": "armoured", "stage": 2, "parent": "Breakthrough Armoured Squad", "branch": "breakthrough", "xp": 900, "requirements": {"kills": 3, "attacking_wins": 3}, "bonuses": _stats(attack=2, defense=2), "function": "Stronger versus entrenched enemies."},

    # Aerial
    "Rapid Insertion Squad": {"family": "aerial", "stage": 1, "parent": None, "branch": "rapid", "xp": 450, "requirements": {"battles_fought": 3, "mobile_attack_wins": 2}, "bonuses": _stats(speed=2, attack=1), "function": "Faster strike timing."},
    "Recon Aerial Squad": {"family": "aerial", "stage": 1, "parent": None, "branch": "recon", "xp": 450, "requirements": {"battles_fought": 2, "recon_successes": 2}, "bonuses": _stats(recon=2, speed=1), "function": "Better battlefield spotting."},
    "Strike Air Cavalry Squad": {"family": "aerial", "stage": 2, "parent": "Rapid Insertion Squad", "branch": "rapid", "xp": 900, "requirements": {"mobile_attack_wins": 4}, "bonuses": _stats(attack=2, speed=1, morale=1), "function": "Better offensive insertion."},
    "Raid Aerial Squad": {"family": "aerial", "stage": 2, "parent": "Rapid Insertion Squad", "branch": "rapid", "xp": 900, "requirements": {"kills": 2, "mobile_attack_wins": 2}, "bonuses": _stats(attack=3, speed=1), "function": "Hit-and-run killer."},
    "Hunter Recon Squad": {"family": "aerial", "stage": 2, "parent": "Recon Aerial Squad", "branch": "recon", "xp": 900, "requirements": {"revealed_target_attacks": 2}, "bonuses": _stats(recon=2, attack=2), "function": "Stronger combat after spotting."},
    "Pathfinder Aerial Squad": {"family": "aerial", "stage": 2, "parent": "Recon Aerial Squad", "branch": "recon", "xp": 900, "requirements": {"recon_successes": 3, "support_actions": 1}, "bonuses": _stats(recon=3, morale=1), "function": "Superior team intel support."},

    # Ranger
    "Deep Recon Ranger Squad": {"family": "ranger", "stage": 1, "parent": None, "branch": "deep_recon", "xp": 450, "requirements": {"recon_successes": 2, "battles_fought": 2}, "bonuses": _stats(recon=2, speed=1), "function": "Best scouting profile."},
    "Survival Ranger Squad": {"family": "ranger", "stage": 1, "parent": None, "branch": "survival", "xp": 450, "requirements": {"recon_successes": 2, "battles_fought": 2, "defensive_survivals": 2}, "bonuses": _stats(defense=1, morale=2), "function": "Better sustain in campaigns."},
    "Pathfinder Ranger Squad": {"family": "ranger", "stage": 2, "parent": "Deep Recon Ranger Squad", "branch": "deep_recon", "xp": 900, "requirements": {"revealed_target_attacks": 3}, "bonuses": _stats(recon=3, speed=1), "function": "Maximum battlefield awareness."},
    "Hunter-Killer Ranger Squad": {"family": "ranger", "stage": 2, "parent": "Deep Recon Ranger Squad", "branch": "deep_recon", "xp": 900, "requirements": {"revealed_target_attacks": 2, "battles_won": 2}, "bonuses": _stats(attack=2, recon=2), "function": "Recon-fed attack specialist."},
    "Guerrilla Ranger Squad": {"family": "ranger", "stage": 2, "parent": "Survival Ranger Squad", "branch": "survival", "xp": 900, "requirements": {"mobile_attack_wins": 2}, "bonuses": _stats(attack=2, speed=1), "function": "Harassment warfare."},
    "Frontier Ranger Squad": {"family": "ranger", "stage": 2, "parent": "Survival Ranger Squad", "branch": "survival", "xp": 900, "requirements": {"battles_fought": 4}, "bonuses": _stats(attack=1, defense=1, morale=2), "function": "Long-campaign endurance unit."},

    # Artillery
    "Mobile Battery": {"family": "artillery", "stage": 1, "parent": None, "branch": "mobile", "xp": 450, "requirements": {"armed_attacks": 3, "mobile_attack_wins": 1}, "bonuses": _stats(speed=1, attack=2), "function": "Less punishing repositioning."},
    "Siege Battery": {"family": "artillery", "stage": 1, "parent": None, "branch": "siege", "xp": 450, "requirements": {"armed_attacks": 3, "stationary_armed_wins": 2}, "bonuses": _stats(attack=3, defense=1), "function": "Brutal static firepower."},
    "Self-Propelled Battery": {"family": "artillery", "stage": 2, "parent": "Mobile Battery", "branch": "mobile", "xp": 900, "requirements": {"mobile_attack_wins": 2}, "bonuses": _stats(attack=2, speed=1, defense=1), "function": "Most responsive artillery form."},
    "Rocket Battery": {"family": "artillery", "stage": 2, "parent": "Mobile Battery", "branch": "mobile", "xp": 900, "requirements": {"splash_multi_hits": 3}, "bonuses": _stats(attack=3, recon=1), "function": "Wider strike pressure."},
    "Heavy Siege Battery": {"family": "artillery", "stage": 2, "parent": "Siege Battery", "branch": "siege", "xp": 900, "requirements": {"kills": 2, "stationary_armed_wins": 1}, "bonuses": _stats(attack=4, defense=1), "function": "Maximum anti-position devastation."},
    "Precision Battery": {"family": "artillery", "stage": 2, "parent": "Siege Battery", "branch": "siege", "xp": 900, "requirements": {"armed_attacks": 6}, "bonuses": _stats(attack=3, recon=1), "function": "More focused elimination power."},

    # Engineering
    "Fortification Engineer Squad": {"family": "engineering", "stage": 1, "parent": None, "branch": "fortification", "xp": 450, "requirements": {"support_actions": 2, "battles_fought": 2, "fortified_actions": 2}, "bonuses": _stats(defense=2, morale=1), "function": "Better terrain shaping."},
    "Logistics Engineer Squad": {"family": "engineering", "stage": 1, "parent": None, "branch": "logistics", "xp": 450, "requirements": {"support_actions": 2, "battles_fought": 2, "repair_actions": 2}, "bonuses": _stats(defense=1, supply=1, morale=1), "function": "Better sustain support."},
    "Siege Engineer Squad": {"family": "engineering", "stage": 2, "parent": "Fortification Engineer Squad", "branch": "fortification", "xp": 900, "requirements": {"fortified_actions": 3, "battles_fought": 3}, "bonuses": _stats(attack=1, defense=2), "function": "Strong front support works."},
    "Bastion Engineer Squad": {"family": "engineering", "stage": 2, "parent": "Fortification Engineer Squad", "branch": "fortification", "xp": 900, "requirements": {"defensive_survivals": 2, "fortified_actions": 2}, "bonuses": _stats(defense=3, morale=1), "function": "Best defensive infrastructure unit."},
    "Recovery Engineer Squad": {"family": "engineering", "stage": 2, "parent": "Logistics Engineer Squad", "branch": "logistics", "xp": 900, "requirements": {"repair_actions": 3}, "bonuses": _stats(defense=1, supply=2), "function": "Best repair/recovery unit."},
    "Combat Support Engineer Squad": {"family": "engineering", "stage": 2, "parent": "Logistics Engineer Squad", "branch": "logistics", "xp": 900, "requirements": {"support_actions": 3, "battles_fought": 3}, "bonuses": _stats(attack=2, defense=1), "function": "More frontline-capable engineers."},

    # Special Operations
    "Infiltration Team": {"family": "special_ops", "stage": 1, "parent": None, "branch": "infiltration", "xp": 450, "requirements": {"battles_won": 3, "revealed_target_attacks": 2}, "bonuses": _stats(recon=2, attack=1), "function": "Better setup-based warfare."},
    "Direct Action Team": {"family": "special_ops", "stage": 1, "parent": None, "branch": "direct_action", "xp": 450, "requirements": {"battles_won": 3, "kills": 2}, "bonuses": _stats(attack=3, morale=1), "function": "Stronger shock engagements."},
    "Shadow Operations Team": {"family": "special_ops", "stage": 2, "parent": "Infiltration Team", "branch": "infiltration", "xp": 900, "requirements": {"revealed_target_attacks": 3, "battles_won": 3}, "bonuses": _stats(recon=2, attack=2), "function": "Elite stealth-hunter profile."},
    "Saboteur Team": {"family": "special_ops", "stage": 2, "parent": "Infiltration Team", "branch": "infiltration", "xp": 900, "requirements": {"kills": 2, "revealed_target_attacks": 2}, "bonuses": _stats(attack=3, recon=1), "function": "Better precision disruption."},
    "Black Ops Strike Team": {"family": "special_ops", "stage": 2, "parent": "Direct Action Team", "branch": "direct_action", "xp": 900, "requirements": {"attacking_wins": 3}, "bonuses": _stats(attack=4, morale=1), "function": "Maximum direct violence."},
    "Counter-Command Team": {"family": "special_ops", "stage": 2, "parent": "Direct Action Team", "branch": "direct_action", "xp": 900, "requirements": {"kills": 2, "battles_won": 4}, "bonuses": _stats(attack=3, recon=1, morale=1), "function": "Anti-elite hunter."},
}


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        if key in row.keys():
            return row[key]
    except Exception:
        pass
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def resolve_veterancy_tier(xp: int) -> str:
    xp = max(0, int(xp or 0))
    tier = "Green"
    for name in VETERANCY_ORDER:
        if xp >= VETERANCY_THRESHOLDS[name]:
            tier = name
    return tier


def next_tier_threshold(xp: int) -> int:
    xp = int(xp or 0)
    for name in VETERANCY_ORDER:
        threshold = VETERANCY_THRESHOLDS[name]
        if xp < threshold:
            return threshold
    return VETERANCY_THRESHOLDS["Legendary"]


def default_unit_name(brigade: str) -> str:
    return FAMILY_CONFIG.get(brigade, FAMILY_CONFIG["infantry"])["base_unit"]


def family_name(brigade: str) -> str:
    cfg = FAMILY_CONFIG.get(brigade)
    return cfg["family"] if cfg else get_brigade(brigade)["name"]


def parse_record(raw: Any) -> Dict[str, Any]:
    record = deepcopy(DEFAULT_COMBAT_RECORD)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if isinstance(raw, dict):
        record.update(raw)
    return record


def parse_text_array(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(v) for v in raw if v]
    if isinstance(raw, tuple):
        return [str(v) for v in raw if v]
    return [str(raw)]


def progression_defaults(brigade: str) -> Dict[str, Any]:
    return {
        "brigade_family": family_name(brigade),
        "unit_name": default_unit_name(brigade),
        "xp": 0,
        "veterancy_tier": "Green",
        "evolution_stage": 0,
        "evolution_branch": None,
        "evolution_path": [],
        "combat_record": deepcopy(DEFAULT_COMBAT_RECORD),
        "unlocked_evolutions": [],
        "capstone_unlocked": False,
    }


def _stat_sum(*bonus_sets: Dict[str, int]) -> Dict[str, int]:
    merged = {key: 0 for key in STAT_KEYS}
    for bonuses in bonus_sets:
        for key, val in (bonuses or {}).items():
            if key in merged:
                merged[key] += int(val or 0)
    return {k: v for k, v in merged.items() if v}


def _tier_at_least(tier: str, target: str) -> bool:
    return VETERANCY_ORDER.index(tier) >= VETERANCY_ORDER.index(target)


def family_stat_bonus(brigade: str, tier: str) -> Dict[str, int]:
    cfg = FAMILY_CONFIG.get(brigade, {})
    table = cfg.get("family_stat_bonuses", {})
    bonuses: List[Dict[str, int]] = []
    for t in VETERANCY_ORDER:
        if _tier_at_least(tier, t):
            bonuses.append(table.get(t, {}))
    return _stat_sum(*bonuses)


def evolution_bonus(unit_name: str) -> Dict[str, int]:
    evo = EVOLUTIONS.get(unit_name)
    return dict(evo.get("bonuses", {})) if evo else {}


def total_bonus(row: Any) -> Dict[str, int]:
    brigade = _row_get(row, "brigade", "infantry")
    xp = _row_get(row, "xp", 0)
    tier = resolve_veterancy_tier(xp)
    unit_name = _row_get(row, "unit_name", default_unit_name(brigade))
    return _stat_sum(
        VETERANCY_BONUSES.get(tier, {}),
        family_stat_bonus(brigade, tier),
        evolution_bonus(unit_name),
    )


def effective_stats(row: Any) -> Dict[str, int]:
    bonuses = total_bonus(row)
    return {key: max(1, int(_row_get(row, key, 10) or 10) + bonuses.get(key, 0)) for key in STAT_KEYS}


def dig_in_bonus(row: Any) -> int:
    if _row_get(row, "brigade") != "infantry":
        return 0
    tier = resolve_veterancy_tier(_row_get(row, "xp", 0))
    if _tier_at_least(tier, "Elite"):
        return 6
    if _tier_at_least(tier, "Hardened"):
        return 5
    return 4


def attack_roll_bonus(row: Any, turn_number: int = 0) -> int:
    brigade = _row_get(row, "brigade", "infantry")
    tier = resolve_veterancy_tier(_row_get(row, "xp", 0))
    record = parse_record(_row_get(row, "combat_record", {}))
    moved = int(_row_get(row, "hexes_moved_this_turn", 0) or 0)
    armed = bool(_row_get(row, "artillery_armed", False))
    bonus = 0

    if brigade == "armoured":
        if _tier_at_least(tier, "Elite") and moved == 0:
            bonus += 2
        if _tier_at_least(tier, "Legendary") and record.get("breakthrough_ready"):
            bonus += 3
    elif brigade == "aerial":
        if _tier_at_least(tier, "Elite") and moved > 0:
            bonus += 2
        if _tier_at_least(tier, "Legendary") and record.get("last_recon_turn") == turn_number:
            bonus += 2
    elif brigade == "ranger":
        if _tier_at_least(tier, "Legendary") and record.get("last_recon_turn") == turn_number:
            bonus += 2
    elif brigade == "artillery" and armed:
        if _tier_at_least(tier, "Hardened"):
            bonus += 1
        if _tier_at_least(tier, "Veteran"):
            bonus += 2
            if moved == 0:
                bonus += 1
    elif brigade == "special_ops":
        if _tier_at_least(tier, "Legendary") and record.get("last_recon_turn") == turn_number:
            bonus += 3
    elif brigade == "infantry":
        if _tier_at_least(tier, "Legendary") and _row_get(row, "is_dug_in", False):
            bonus += 2
    return bonus


def defense_roll_bonus(row: Any) -> int:
    brigade = _row_get(row, "brigade", "infantry")
    tier = resolve_veterancy_tier(_row_get(row, "xp", 0))
    moved = int(_row_get(row, "hexes_moved_this_turn", 0) or 0)
    if brigade == "infantry" and _tier_at_least(tier, "Elite") and moved > 0:
        return 2
    return 0


def splash_damage(row: Any) -> int:
    if _row_get(row, "brigade") != "artillery":
        return 10
    tier = resolve_veterancy_tier(_row_get(row, "xp", 0))
    if tier == "Legendary":
        return 16
    if tier == "Elite":
        return 14
    return 10


def eligible_evolutions(row: Any) -> List[Dict[str, Any]]:
    brigade = _row_get(row, "brigade", "infantry")
    xp = int(_row_get(row, "xp", 0) or 0)
    stage = int(_row_get(row, "evolution_stage", 0) or 0)
    unit_name = _row_get(row, "unit_name", default_unit_name(brigade))
    record = parse_record(_row_get(row, "combat_record", {}))
    choices = []
    for name, evo in EVOLUTIONS.items():
        if evo["family"] != brigade:
            continue
        if evo["stage"] != stage + 1:
            continue
        if evo["stage"] == 1 and evo["parent"] is not None:
            continue
        if evo["stage"] == 2 and evo["parent"] != unit_name:
            continue
        if xp < evo["xp"]:
            continue
        if any(int(record.get(k, 0) or 0) < int(v) for k, v in evo.get("requirements", {}).items()):
            continue
        choices.append({"name": name, **evo})
    return choices


def locked_evolution_brief(row: Any) -> List[Dict[str, Any]]:
    brigade = _row_get(row, "brigade", "infantry")
    stage = int(_row_get(row, "evolution_stage", 0) or 0)
    unit_name = _row_get(row, "unit_name", default_unit_name(brigade))
    choices = []
    for name, evo in EVOLUTIONS.items():
        if evo["family"] != brigade or evo["stage"] != stage + 1:
            continue
        if evo["stage"] == 1 and evo["parent"] is not None:
            continue
        if evo["stage"] == 2 and evo["parent"] != unit_name:
            continue
        choices.append({"name": name, **evo})
    return choices


def refresh_unlocked(row: Any) -> List[str]:
    return [e["name"] for e in eligible_evolutions(row)]


async def sync_progression(conn, squadron_id: int) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow("SELECT * FROM squadrons WHERE id=$1", squadron_id)
    if not row:
        return None
    brigade = row["brigade"]
    xp = int(_row_get(row, "xp", 0) or 0)
    tier = resolve_veterancy_tier(xp)
    unlocked = refresh_unlocked(row)
    capstone = tier == "Legendary"
    await conn.execute(
        """
        UPDATE squadrons
        SET brigade_family=COALESCE(brigade_family, $1),
            unit_name=COALESCE(unit_name, $2),
            veterancy_tier=$3,
            unlocked_evolutions=$4::text[],
            capstone_unlocked=$5
        WHERE id=$6
        """,
        family_name(brigade), default_unit_name(brigade), tier, unlocked, capstone, squadron_id,
    )
    return {"tier": tier, "unlocked": unlocked, "capstone_unlocked": capstone}


async def award_action_progress(conn, squadron_id: int, action: str, turn_number: int = -1, xp: int = 0) -> int:
    row = await conn.fetchrow("SELECT id, combat_record, xp FROM squadrons WHERE id=$1", squadron_id)
    if not row:
        return 0
    record = parse_record(row["combat_record"])
    key_map = {
        "recon": ("recon_successes", "last_recon_turn"),
        "support": ("support_actions", "last_support_turn"),
        "fortify": ("fortified_actions", "last_fortify_turn"),
        "repair": ("repair_actions", "last_support_turn"),
        "scavenge": (None, "last_scavenge_turn"),
    }
    counter_key, turn_key = key_map.get(action, (None, None))
    if counter_key:
        record[counter_key] = int(record.get(counter_key, 0) or 0) + 1
    if action == "repair":
        record["support_actions"] = int(record.get("support_actions", 0) or 0) + 1
    if turn_key and turn_number >= 0:
        record[turn_key] = turn_number
    new_xp = int(row["xp"] or 0) + max(0, int(xp or 0))
    await conn.execute(
        "UPDATE squadrons SET combat_record=$1::jsonb, xp=$2 WHERE id=$3",
        json.dumps(record), new_xp, squadron_id,
    )
    await sync_progression(conn, squadron_id)
    return max(0, int(xp or 0))


def combat_xp_award(row: Any, result: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    brigade = _row_get(row, "brigade", "infantry")
    record = parse_record(_row_get(row, "combat_record", {}))
    destroyed = bool(context.get("destroyed_enemy"))
    won = getattr(result, "outcome", "") == "attacker_wins"
    survived_low = bool(context.get("survived_low_hp"))
    stronger = bool(context.get("stronger_enemy"))
    moved = int(_row_get(row, "hexes_moved_this_turn", 0) or 0)
    armed = bool(_row_get(row, "artillery_armed", False))
    dug_in = bool(_row_get(row, "is_dug_in", False))
    turn_number = int(context.get("turn_number", -1))
    splash_hits = int(context.get("splash_hits", 0) or 0)
    damage_taken = int(context.get("damage_taken", 0) or 0)

    xp_parts = [("participation", 12)]
    if won:
        xp_parts.append(("victory", 10))
    if destroyed:
        xp_parts.append(("kill", 18))
    if survived_low:
        xp_parts.append(("low-hp survival", 8))
    if stronger:
        xp_parts.append(("stronger enemy", 8))

    major_bonus = None
    if brigade == "infantry":
        if won and dug_in:
            major_bonus = ("dug-in win", 6)
        elif survived_low:
            major_bonus = ("no-retreat survival", 8)
    elif brigade == "armoured":
        if destroyed and won:
            major_bonus = ("attacking kill", 10)
        elif damage_taken >= 18 and not context.get("unit_destroyed"):
            major_bonus = ("heavy damage absorbed", 8)
    elif brigade == "aerial":
        if record.get("last_recon_turn") == turn_number:
            major_bonus = ("revealed target attack", 6)
        elif won and moved >= 2:
            major_bonus = ("two-hex assault", 8)
    elif brigade == "ranger":
        if record.get("last_recon_turn") == turn_number:
            major_bonus = ("recon-led engagement", 6 if not won else 8)
    elif brigade == "artillery":
        if armed:
            major_bonus = ("armed hit", 8)
            if won and moved == 0:
                major_bonus = ("stationary armed win", 6)
    elif brigade == "engineering":
        if record.get("last_fortify_turn") == turn_number or record.get("last_support_turn") == turn_number:
            major_bonus = ("prepared support survival", 6)
        elif context.get("adjacent_friendly"):
            major_bonus = ("adjacent support combat", 5)
    elif brigade == "special_ops":
        if destroyed and result.attacker_roll >= result.defender_roll:
            major_bonus = ("first-strike kill", 10)
        elif won and record.get("last_recon_turn") == turn_number:
            major_bonus = ("setup win", 8)

    if major_bonus:
        xp_parts.append(major_bonus)
    if brigade == "artillery" and splash_hits > 0:
        xp_parts.append((f"splash x{splash_hits}", 4 * splash_hits))

    record["battles_fought"] = int(record.get("battles_fought", 0) or 0) + 1
    if won:
        record["battles_won"] = int(record.get("battles_won", 0) or 0) + 1
        record["attacking_wins"] = int(record.get("attacking_wins", 0) or 0) + 1
    if destroyed:
        record["kills"] = int(record.get("kills", 0) or 0) + 1
    if dug_in or survived_low:
        record["defensive_survivals"] = int(record.get("defensive_survivals", 0) or 0) + 1
    if armed:
        record["armed_attacks"] = int(record.get("armed_attacks", 0) or 0) + 1
    if moved > 0 and won:
        record["mobile_attack_wins"] = int(record.get("mobile_attack_wins", 0) or 0) + 1
    if record.get("last_recon_turn") == turn_number:
        record["revealed_target_attacks"] = int(record.get("revealed_target_attacks", 0) or 0) + 1
    if damage_taken >= 18 and not context.get("unit_destroyed"):
        record["heavy_damage_survivals"] = int(record.get("heavy_damage_survivals", 0) or 0) + 1
    if armed and moved == 0 and won:
        record["stationary_armed_wins"] = int(record.get("stationary_armed_wins", 0) or 0) + 1
    if splash_hits >= 2:
        record["splash_multi_hits"] = int(record.get("splash_multi_hits", 0) or 0) + 1

    if brigade == "armoured":
        record["breakthrough_ready"] = bool(won)

    return {
        "xp": sum(v for _, v in xp_parts),
        "parts": xp_parts,
        "record": record,
    }


async def award_combat_progress(conn, squadron_id: int, result: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    row = await conn.fetchrow("SELECT * FROM squadrons WHERE id=$1", squadron_id)
    if not row:
        return {"xp": 0, "tier_changed": False, "unlocked": []}
    before_tier = resolve_veterancy_tier(row["xp"] or 0)
    award = combat_xp_award(row, result, context)
    new_xp = int(row["xp"] or 0) + award["xp"]
    new_tier = resolve_veterancy_tier(new_xp)
    await conn.execute(
        "UPDATE squadrons SET xp=$1, veterancy_tier=$2, combat_record=$3::jsonb WHERE id=$4",
        new_xp, new_tier, json.dumps(award["record"]), squadron_id,
    )
    synced = await sync_progression(conn, squadron_id) or {}
    return {
        "xp": award["xp"],
        "parts": award["parts"],
        "tier": new_tier,
        "tier_changed": before_tier != new_tier,
        "unlocked": synced.get("unlocked", []),
    }


async def apply_evolution(conn, squadron_id: int, target_name: str) -> Dict[str, Any]:
    row = await conn.fetchrow("SELECT * FROM squadrons WHERE id=$1", squadron_id)
    if not row:
        raise ValueError("Unit not found.")
    allowed = {e["name"]: e for e in eligible_evolutions(row)}
    if target_name not in allowed:
        raise ValueError("Evolution is not unlocked for this unit.")
    evo = allowed[target_name]
    path = parse_text_array(row["evolution_path"])
    path.append(target_name)
    await conn.execute(
        """
        UPDATE squadrons
        SET unit_name=$1,
            evolution_stage=$2,
            evolution_branch=$3,
            evolution_path=$4::text[]
        WHERE id=$5
        """,
        target_name, evo["stage"], evo["branch"], path, squadron_id,
    )
    await sync_progression(conn, squadron_id)
    return evo


def format_requirements(evo: Dict[str, Any], record: Dict[str, Any], xp: int) -> str:
    parts = [f"XP {min(xp, evo['xp'])}/{evo['xp']}"]
    for key, needed in evo.get("requirements", {}).items():
        current = int(record.get(key, 0) or 0)
        label = key.replace("_", " ").title()
        parts.append(f"{label} {min(current, needed)}/{needed}")
    return " | ".join(parts)

