"""
Views — Victoria-style persistent button command panel.
All labels are theme-aware. Planet context is always the active planet.
"""

import random
import discord
from discord.ui import View, Button

from utils.db import get_pool, get_theme, get_active_planet_id, has_active_contracts
from utils.brigades import BRIGADES


def _bar(val: int, length: int = 12) -> str:
    filled = max(0, min(length, int((val / 20) * length)))
    return "▓" * filled + "░" * (length - filled)


def _mini_bar(val: int, max_val: int = 20, length: int = 8) -> str:
    filled = max(0, min(length, int((val / max_val) * length)))
    return "█" * filled + "░" * (length - filled)


async def _safe(interaction: discord.Interaction, coro):
    try:
        await coro
    except Exception as e:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ══════════════════════════════════════════════════════════════════════════════

class MainMenuView(View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="🗺️ Map",         style=discord.ButtonStyle.primary,   custom_id="menu_map",              row=0)
    async def view_map(self, i: discord.Interaction, b: Button):
        await _safe(i, _send_map(i))

    @discord.ui.button(label="🪐 System",      style=discord.ButtonStyle.secondary, custom_id="menu_planetary_system", row=0)
    async def planetary_system(self, i: discord.Interaction, b: Button):
        await _safe(i, _send_overview(i))

    @discord.ui.button(label="🪖 My Unit",     style=discord.ButtonStyle.primary,   custom_id="menu_my_unit",          row=0)
    async def my_unit(self, i: discord.Interaction, b: Button):
        await _safe(i, _send_unit_panel(i))

    @discord.ui.button(label="📋 Contract",    style=discord.ButtonStyle.secondary, custom_id="menu_status",           row=1)
    async def war_status(self, i: discord.Interaction, b: Button):
        await _safe(i, _send_contract_board(i))

    @discord.ui.button(label="📜 Combat Log",  style=discord.ButtonStyle.secondary, custom_id="menu_log",              row=1)
    async def combat_log(self, i: discord.Interaction, b: Button):
        await _safe(i, _send_combat_log(i))

    @discord.ui.button(label="🏆 Leaderboard", style=discord.ButtonStyle.secondary, custom_id="menu_leaderboard",      row=1)
    async def leaderboard(self, i: discord.Interaction, b: Button):
        await _safe(i, _send_leaderboard(i))


# ── Map ────────────────────────────────────────────────────────────────────────

async def _send_map(i: discord.Interaction):
    await i.response.defer(ephemeral=True, thinking=True)
    pool = await get_pool()
    async with pool.acquire() as conn:
        theme = await get_theme(conn, i.guild_id)
        try:
            from utils.map_render import render_map_for_guild
            buf = await render_map_for_guild(i.guild_id, conn)
            f   = discord.File(buf, filename="warmap.png")
            embed = discord.Embed(
                title=f"🗺️  Tactical Map — {theme.get('bot_name','WARBOT')}",
                color=theme.get("color", 0xAA2222))
            embed.set_image(url="attachment://warmap.png")
            embed.set_footer(text=theme.get("flavor_text",""))
            await i.followup.send(embed=embed, file=f, ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Map render failed: {e}", ephemeral=True)


async def _send_overview(i: discord.Interaction):
    await i.response.defer(ephemeral=True, thinking=True)
    pool = await get_pool()
    async with pool.acquire() as conn:
        theme = await get_theme(conn, i.guild_id)
        try:
            from utils.map_render import render_overview_for_guild
            buf = await render_overview_for_guild(i.guild_id, conn)
            f   = discord.File(buf, filename="overview.png")
            embed = discord.Embed(
                title=f"🪐  Planetary Theatres — {theme.get('bot_name','WARBOT')}",
                color=theme.get("color", 0xAA2222))
            embed.set_image(url="attachment://overview.png")
            await i.followup.send(embed=embed, file=f, ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Overview render failed: {e}", ephemeral=True)


# ── Unit panel ────────────────────────────────────────────────────────────────

async def _send_unit_panel(i: discord.Interaction):
    from cogs.squadron_cog import send_unit_panel
    await send_unit_panel(i, i.guild_id)


# ── Unit action sub-panel ─────────────────────────────────────────────────────

class UnitActionView(View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @discord.ui.button(label="📍 Move Unit",  style=discord.ButtonStyle.primary,   custom_id="unit_action_move")
    async def move_unit(self, i: discord.Interaction, b: Button):
        await i.response.send_modal(MoveModal(self.guild_id))

    @discord.ui.button(label="🔍 Scavenge",  style=discord.ButtonStyle.secondary, custom_id="unit_action_scavenge")
    async def scavenge(self, i: discord.Interaction, b: Button):
        await _safe(i, _do_scavenge(i, self.guild_id))

    @discord.ui.button(label="← Back",       style=discord.ButtonStyle.secondary, custom_id="unit_action_back")
    async def back(self, i: discord.Interaction, b: Button):
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme = await get_theme(conn, self.guild_id)
            embed = await build_menu_embed(self.guild_id, conn, theme)
        await i.response.edit_message(embed=embed, view=MainMenuView(self.guild_id))


# ── Move modal ────────────────────────────────────────────────────────────────

class MoveModal(discord.ui.Modal, title="Move Unit"):
    destination = discord.ui.TextInput(
        label="Target Hex Address",
        placeholder="e.g. 3,-2",
        max_length=12, required=True)

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, i: discord.Interaction):
        dest = str(self.destination).strip()
        from utils.hexmap import is_valid, hex_distance
        if not is_valid(dest):
            await i.response.send_message(
                "❌ Invalid hex. Use format `gq,gr` e.g. `3,-2`.", ephemeral=True); return
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme     = await get_theme(conn, self.guild_id)
            planet_id = await get_active_planet_id(conn, self.guild_id)
            sq        = await conn.fetchrow(
                "SELECT * FROM squadrons "
                "WHERE guild_id=$1 AND planet_id=$2 AND owner_id=$3 AND is_active=TRUE LIMIT 1",
                self.guild_id, planet_id, i.user.id)
            if not sq:
                await i.response.send_message("No active unit.", ephemeral=True); return
            if sq["in_transit"]:
                await i.response.send_message("Already in transit.", ephemeral=True); return

            dist = hex_distance(sq["hex_address"], dest)
            if dist == 0:
                await i.response.send_message("Already at that hex.", ephemeral=True); return

            budget    = sq["speed"] // 2
            remaining = max(0, budget - sq["hexes_moved_this_turn"])
            if dist > remaining:
                await i.response.send_message(
                    f"❌ That hex is **{dist}** away but you only have "
                    f"**{remaining}/{budget}** hexes remaining this turn.", ephemeral=True); return

            await conn.execute(
                "UPDATE squadrons SET hex_address=$1, is_dug_in=FALSE, "
                "hexes_moved_this_turn=hexes_moved_this_turn+$2 WHERE id=$3",
                dest, dist, sq["id"])
            await i.response.send_message(f"✅ Moved to `{dest}`.", ephemeral=True)


# ── Scavenge ──────────────────────────────────────────────────────────────────

async def _do_scavenge(i: discord.Interaction, guild_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        theme     = await get_theme(conn, guild_id)
        planet_id = await get_active_planet_id(conn, guild_id)
        turn_count = await conn.fetchval(
            "SELECT COUNT(*) FROM turn_history WHERE guild_id=$1 AND planet_id=$2",
            guild_id, planet_id) or 0
        sq = await conn.fetchrow(
            "SELECT * FROM squadrons "
            "WHERE guild_id=$1 AND planet_id=$2 AND owner_id=$3 AND is_active=TRUE LIMIT 1",
            guild_id, planet_id, i.user.id)
        if not sq:
            await i.response.send_message("No active unit.", ephemeral=True); return
        if sq["last_scavenged_turn"] >= turn_count:
            await i.response.send_message("Already scavenged this turn.", ephemeral=True); return
        gain = random.randint(1, 5) + (sq["recon"] // 5)
        new_supply = min(20, sq["supply"] + gain)
        await conn.execute(
            "UPDATE squadrons SET supply=$1, last_scavenged_turn=$2 WHERE id=$3",
            new_supply, turn_count, sq["id"])
    await i.response.send_message(
        f"🔍 Scavenged **+{gain}** supply → `{new_supply}/20`.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
# CONTRACT BOARD
# ══════════════════════════════════════════════════════════════════════════════

DEPLOYABLE_STATUSES = ("deployable", "active")
BOARD_STATUSES = ("open", "accepting", "locked", "deployable", "active")


async def fetch_contract(conn, guild_id: int, contract_id: int):
    return await conn.fetchrow(
        "SELECT * FROM contracts WHERE guild_id=$1 AND id=$2",
        guild_id, contract_id)


async def fetch_board_contracts(conn, guild_id: int, limit: int = 25):
    return await conn.fetch(
        """
        SELECT c.*,
               COUNT(ca.player_id)::INT AS accepted_count
        FROM contracts c
        LEFT JOIN contract_acceptances ca
          ON ca.guild_id=c.guild_id AND ca.contract_id=c.id
        WHERE c.guild_id=$1
          AND c.status = ANY($2::text[])
        GROUP BY c.id
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT $3
        """,
        guild_id, list(BOARD_STATUSES), limit)


def _status_icon(status: str) -> str:
    return {
        "open":               "🔓",
        "accepting":          "✅",
        "locked":             "🔒",
        "deployable":         "🚀",
        "active":             "⚔️",
        "suspended":          "⏸️",
        "cancelled":          "🚫",
        "concluded_success":  "🏆",
        "concluded_failure":  "💀",
    }.get(status, "•")


def _difficulty_icon(difficulty: str) -> str:
    return {
        "trivial":  "🟢",
        "standard": "🟡",
        "hard":     "🟠",
        "extreme":  "🔴",
        "suicide":  "💀",
    }.get((difficulty or "standard").lower(), "🟡")


# ── Live public contract board (markdown only, no buttons) ─────────────────

def build_public_contract_board_embed(theme: dict, rows, active_enemies: list = None) -> discord.Embed:
    """
    The persistent live board posted in the contract channel.
    Shows all contracts as a markdown list. No action buttons — players interact
    via the 📋 Contract button on the main menu command centre.
    """
    bot_name = theme.get("bot_name", "WARBOT")
    embed = discord.Embed(
        title="📋  Contract Board",
        color=theme.get("color", 0xAA2222),
    )

    if not rows:
        embed.description = "*No contracts posted yet. Stand by for GM briefing.*"
        embed.set_footer(text=f"{bot_name}  ·  Press 📋 Contract on the command centre to interact.")
        return embed

    contract_lines = []
    for c in rows:
        icon     = _status_icon(c["status"])
        diff     = _difficulty_icon(c.get("difficulty", "standard"))
        cap      = c["deployment_capacity"] or 0
        dep      = c["deployed_units"] or 0
        accepted = c.get("accepted_count", 0)
        status_label = c["status"].replace("_", " ").title()
        bar_fill = int(8 * dep / cap) if cap > 0 else 0
        dep_bar  = "█" * bar_fill + "░" * (8 - bar_fill)

        contract_lines.append(
            f"{icon}{diff} **#{c['id']:03d} — {c['title']}**\n"
            f"  `{status_label}`  ·  {c['planet_system']}  ·  vs **{c['enemy']}**\n"
            f"  Enlistees: **{accepted}**  ·  Deployed: `{dep_bar}` {dep}/{cap}"
        )

    embed.description = "\n\n".join(contract_lines)

    if active_enemies:
        enemy_lines = []
        for e in active_enemies[:8]:
            hp  = e.get("hp", 100)
            bar = _mini_bar(hp, max_val=100, length=8)
            enemy_lines.append(f"🔴 **{e['unit_type']}** @ `{e['hex_address']}`  HP `{bar}` {hp}/100")
        embed.add_field(
            name="⚠️  Active Enemy Contact",
            value="\n".join(enemy_lines),
            inline=False,
        )

    embed.set_footer(text=f"{bot_name}  ·  {len(rows)} contract(s) listed  ·  Use 📋 Contract on the command centre to enlist or deploy.")
    return embed


# ── Ephemeral per-contract detail panel ───────────────────────────────────────

def build_contract_detail_embed(theme: dict, c, accepted_count: int,
                                 player_accepted: bool = False) -> discord.Embed:
    """Full detail card sent ephemerally when a player selects a contract from the dropdown."""
    icon   = _status_icon(c["status"])
    diff   = _difficulty_icon(c.get("difficulty", "standard"))
    cap    = c["deployment_capacity"] or 0
    dep    = c["deployed_units"] or 0
    fleets = c["fleet_count"] or 0

    bar_fill   = int(12 * dep / cap) if cap > 0 else 0
    dep_bar    = "█" * bar_fill + "░" * (12 - bar_fill)
    fill_pct   = int(dep / cap * 100) if cap > 0 else 0
    slots_left = max(0, cap - dep)
    your_status = "✅ Accepted" if player_accepted else "—"

    embed = discord.Embed(
        title=f"{icon}  CONTRACT #{c['id']:03d}  ·  {c['title']}",
        color=theme.get("color", 0xAA2222),
        description=(
            f"> {diff} **{c['status'].replace('_',' ').title()}**  ·  Planet: **{c['planet_system']}**\n"
            f"> Enemy: **{c['enemy']}**  ·  Difficulty: **{(c.get('difficulty') or 'Standard').title()}**"
            + (f"\n\n*{c['description']}*" if c.get("description") else "")
        ),
    )

    embed.add_field(name="Your Status", value=your_status,                           inline=True)
    embed.add_field(name="Sign-ups",    value=f"**{accepted_count}** commandant(s)", inline=True)
    embed.add_field(name="Fleets",      value=f"**{fleets}** assigned",              inline=True)

    if fleets > 0:
        embed.add_field(
            name=f"Deployment  [{dep_bar}]  {dep}/{cap}  ({fill_pct}%)",
            value=(
                "**All slots filled.**" if slots_left == 0
                else f"**{slots_left}** slot(s) open"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name="Deployment",
            value="Awaiting GM fleet assignment — sign up while acceptance is open.",
            inline=False,
        )

    embed.set_footer(text=f"{theme.get('bot_name','WARBOT')}  ·  Use the buttons below to act on this contract.")
    return embed


# ── Contract board overview embed (shown first in ephemeral board) ─────────

def build_contract_board_embed(theme: dict, rows) -> discord.Embed:
    """Ephemeral overview listing all contracts, with dropdown to drill in."""
    bot_name = theme.get("bot_name", "WARBOT")
    embed = discord.Embed(
        title="📋  Contract Board",
        color=theme.get("color", 0xAA2222),
    )
    if not rows:
        embed.description = "*No contracts on the board yet. Check back when the GM posts one.*"
        embed.set_footer(text=bot_name)
        return embed

    lines = []
    for c in rows:
        icon     = _status_icon(c["status"])
        diff     = _difficulty_icon(c.get("difficulty", "standard"))
        accepted = c.get("accepted_count", 0)
        cap      = c["deployment_capacity"] or 0
        dep      = c["deployed_units"] or 0
        lines.append(
            f"{icon}{diff} **#{c['id']:03d} — {c['title']}**  ·  vs {c['enemy']}\n"
            f"  `{c['status'].replace('_',' ').title()}`  ·  {accepted} enlisted  ·  {dep}/{cap} deployed"
        )

    embed.description = (
        "Select a contract from the dropdown to view full details and take action.\n\n"
        + "\n\n".join(lines)
    )
    embed.set_footer(text=f"{bot_name}  ·  {len(rows)} contract(s) on board")
    return embed


# ── Contract dropdown ─────────────────────────────────────────────────────────

class ContractSelect(discord.ui.Select):
    def __init__(self, rows):
        options = []
        for c in rows[:25]:
            icon = _status_icon(c["status"])
            diff = _difficulty_icon(c.get("difficulty", "standard"))
            cap  = c["deployment_capacity"] or 0
            dep  = c["deployed_units"] or 0
            options.append(discord.SelectOption(
                label=f"{icon} #{c['id']:03d} {c['title']}"[:100],
                value=str(c["id"]),
                description=f"{diff} {c['status'].title()} · vs {c['enemy']} · {dep}/{cap} deployed"[:100],
            ))
        super().__init__(placeholder="Select a contract to view details...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_id = int(self.values[0])
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme  = await get_theme(conn, interaction.guild_id)
            rows   = await fetch_board_contracts(conn, interaction.guild_id)
            c      = next((r for r in rows if r["id"] == selected_id), None)
            accepted_count  = c["accepted_count"] if c else 0
            player_accepted = bool(await conn.fetchval(
                "SELECT 1 FROM contract_acceptances "
                "WHERE guild_id=$1 AND contract_id=$2 AND player_id=$3",
                interaction.guild_id, selected_id, interaction.user.id))

        if not c:
            await interaction.response.send_message("Contract not found.", ephemeral=True)
            return

        detail_embed = build_contract_detail_embed(theme, c, accepted_count, player_accepted)
        await interaction.response.send_message(
            embed=detail_embed,
            view=ContractActionView(interaction.guild_id, selected_id, player_accepted),
            ephemeral=True,
        )


class ContractBoardView(View):
    """Ephemeral board shown to a player — dropdown listing all contracts."""
    def __init__(self, guild_id: int, rows=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        if rows:
            self.add_item(ContractSelect(rows))


async def _send_contract_board(i: discord.Interaction):
    """Send the ephemeral contract board to the requesting player."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        theme = await get_theme(conn, i.guild_id)
        rows  = await fetch_board_contracts(conn, i.guild_id)

    embed = build_contract_board_embed(theme, rows)
    await i.response.send_message(
        embed=embed,
        view=ContractBoardView(i.guild_id, rows),
        ephemeral=True,
    )


# ── Per-contract action view ───────────────────────────────────────────────────

class ContractActionView(View):
    """Sent ephemerally after the player picks a contract from the dropdown."""
    def __init__(self, guild_id: int, contract_id: int, player_accepted: bool = False):
        super().__init__(timeout=300)
        self.guild_id        = guild_id
        self.contract_id     = contract_id
        self.player_accepted = player_accepted

    async def _get_contract(self, i: discord.Interaction):
        pool = await get_pool()
        async with pool.acquire() as conn:
            c        = await fetch_contract(conn, i.guild_id, self.contract_id)
            accepted = bool(await conn.fetchval(
                "SELECT 1 FROM contract_acceptances "
                "WHERE guild_id=$1 AND contract_id=$2 AND player_id=$3",
                i.guild_id, self.contract_id, i.user.id))
        if not c:
            await i.response.send_message("Contract not found — it may have been removed.", ephemeral=True)
            return None, False
        return c, accepted

    async def _refresh(self, i: discord.Interaction, accepted: bool):
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme = await get_theme(conn, i.guild_id)
            rows  = await fetch_board_contracts(conn, i.guild_id)
            c     = next((r for r in rows if r["id"] == self.contract_id), None)
            accepted_count = c["accepted_count"] if c else 0
        if not c:
            await i.response.edit_message(content="Contract no longer available.", embed=None, view=None)
            return
        embed = build_contract_detail_embed(theme, c, accepted_count, player_accepted=accepted)
        await i.response.edit_message(
            embed=embed,
            view=ContractActionView(i.guild_id, self.contract_id, accepted))

    @discord.ui.button(label="✅ Accept",         style=discord.ButtonStyle.success,   row=0)
    async def accept_contract(self, i: discord.Interaction, b: Button):
        c, already = await self._get_contract(i)
        if c is None: return
        if c["status"] not in ("accepting", "open"):
            await i.response.send_message(
                f"Sign-ups are **{c['status']}** for this contract.", ephemeral=True); return
        if already:
            await i.response.send_message("You have already accepted this contract.", ephemeral=True); return
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO contract_acceptances (guild_id, contract_id, player_id) "
                "VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                i.guild_id, c["id"], i.user.id)
        await self._refresh(i, accepted=True)

    @discord.ui.button(label="↩️ Withdraw",        style=discord.ButtonStyle.secondary, row=0)
    async def withdraw_contract(self, i: discord.Interaction, b: Button):
        c, accepted = await self._get_contract(i)
        if c is None: return
        if c["status"] not in ("accepting", "open"):
            await i.response.send_message(
                "Sign-ups are locked — you cannot withdraw now.", ephemeral=True); return
        if not accepted:
            await i.response.send_message("You have not accepted this contract.", ephemeral=True); return
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM contract_acceptances "
                "WHERE guild_id=$1 AND contract_id=$2 AND player_id=$3",
                i.guild_id, c["id"], i.user.id)
        await self._refresh(i, accepted=False)

    @discord.ui.button(label="🚀 Deploy Roster",   style=discord.ButtonStyle.primary,   row=0)
    async def deploy_contract(self, i: discord.Interaction, b: Button):
        c, accepted = await self._get_contract(i)
        if c is None: return
        if not accepted:
            await i.response.send_message(
                "Accept this contract first before deploying.", ephemeral=True); return
        if c["status"] not in DEPLOYABLE_STATUSES:
            await i.response.send_message(
                f"Contract is **{c['status']}** — deployment opens once the GM assigns fleets.",
                ephemeral=True); return
        from cogs.squadron_cog import open_returning_deploy
        await open_returning_deploy(i, self.contract_id)

    @discord.ui.button(label="⚔️ Enlist New Unit", style=discord.ButtonStyle.success,   row=1)
    async def new_unit_contract(self, i: discord.Interaction, b: Button):
        c, accepted = await self._get_contract(i)
        if c is None: return
        if not accepted:
            await i.response.send_message(
                "Accept this contract first, then enlist once fleets are assigned.",
                ephemeral=True); return
        if c["status"] not in DEPLOYABLE_STATUSES:
            await i.response.send_message(
                f"Contract is **{c['status']}** — fleets must be assigned before enlisting.",
                ephemeral=True); return
        await i.response.send_modal(_UnitNameModal(i.guild_id, False, self.contract_id))


# ── Combat log ────────────────────────────────────────────────────────────────

async def _send_combat_log(i: discord.Interaction):
    pool = await get_pool()
    async with pool.acquire() as conn:
        theme     = await get_theme(conn, i.guild_id)
        planet_id = await get_active_planet_id(conn, i.guild_id)
        entries   = await conn.fetch(
            "SELECT turn_number, hex_address, attacker, defender, "
            "attacker_roll, defender_roll, outcome "
            "FROM combat_log WHERE guild_id=$1 AND planet_id=$2 "
            "ORDER BY id DESC LIMIT 15",
            i.guild_id, planet_id)
    if not entries:
        await i.response.send_message("No combat recorded yet.", ephemeral=True); return

    lines = []
    for e in entries:
        outcome_icon = {"attacker_wins": "🟢", "defender_wins": "🔴", "draw": "🟡"}.get(e["outcome"], "⬜")
        margin       = e["attacker_roll"] - e["defender_roll"]
        margin_str   = f"+{margin}" if margin > 0 else str(margin)
        lines.append(
            f"{outcome_icon} **T{e['turn_number']}** · `{e['hex_address']}`\n"
            f"  {e['attacker']} **{e['attacker_roll']}** vs {e['defender']} **{e['defender_roll']}**  ({margin_str})"
        )

    embed = discord.Embed(
        title="📜  Recent Combat",
        description="\n".join(lines),
        color=theme.get("color", 0xAA2222),
    )
    embed.set_footer(text=f"Last {len(entries)} engagements · {theme.get('bot_name','WARBOT')}")
    await i.response.send_message(embed=embed, ephemeral=True)


# ── Leaderboard ───────────────────────────────────────────────────────────────

async def _send_leaderboard(i: discord.Interaction):
    pool = await get_pool()
    async with pool.acquire() as conn:
        theme     = await get_theme(conn, i.guild_id)
        planet_id = await get_active_planet_id(conn, i.guild_id)
        rows      = await conn.fetch(
            "SELECT owner_name, name, attack, defense, speed, morale, supply, recon, "
            "attack+defense+speed+morale+supply+recon AS power "
            "FROM squadrons WHERE guild_id=$1 AND planet_id=$2 AND is_active=TRUE "
            "ORDER BY power DESC LIMIT 10",
            i.guild_id, planet_id)
    if not rows:
        await i.response.send_message("No units enlisted yet.", ephemeral=True); return

    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    for n, r in enumerate(rows):
        prefix    = medals[n] if n < 3 else f"**{n+1}.**"
        power_bar = _mini_bar(r["power"], max_val=120, length=8)
        lines.append(
            f"{prefix} **{r['owner_name']}** — {r['name']}\n"
            f"  `{power_bar}` **{r['power']}** pts"
        )

    embed = discord.Embed(
        title=f"🏆  {theme.get('player_faction','PMC')} Leaderboard",
        description="\n".join(lines),
        color=theme.get("color", 0xAA2222),
    )
    embed.set_footer(text=f"Power = ATK+DEF+SPD+MRL+SUP+RCN · {theme.get('bot_name','WARBOT')}")
    await i.response.send_message(embed=embed, ephemeral=True)


# ── Menu embed builder ────────────────────────────────────────────────────────

async def build_menu_embed(guild_id: int, conn, theme: dict = None) -> discord.Embed:
    if theme is None:
        theme = await get_theme(conn, guild_id)

    planet_id  = await get_active_planet_id(conn, guild_id)
    planet     = await conn.fetchrow(
        "SELECT name, contractor, enemy_type FROM planets WHERE guild_id=$1 AND id=$2",
        guild_id, planet_id)
    cfg        = await conn.fetchrow(
        "SELECT turn_interval_hours, contract_name, operational_tempo, tempo_threshold, fleet_pool_available FROM guild_config WHERE guild_id=$1",
        guild_id)
    is_active  = await has_active_contracts(conn, guild_id)
    turn_count = await conn.fetchval(
        "SELECT COUNT(*) FROM turn_history WHERE guild_id=$1 AND planet_id=$2",
        guild_id, planet_id) or 0
    p_count    = await conn.fetchval(
        "SELECT COUNT(DISTINCT owner_id) FROM squadrons "
        "WHERE guild_id=$1 AND planet_id=$2 AND is_active=TRUE",
        guild_id, planet_id) or 0
    e_count    = await conn.fetchval(
        "SELECT COUNT(*) FROM enemy_units "
        "WHERE guild_id=$1 AND planet_id=$2 AND is_active=TRUE",
        guild_id, planet_id) or 0
    p_hexes    = await conn.fetchval(
        "SELECT COUNT(*) FROM hexes "
        "WHERE guild_id=$1 AND planet_id=$2 AND controller='players'",
        guild_id, planet_id) or 0
    e_hexes    = await conn.fetchval(
        "SELECT COUNT(*) FROM hexes "
        "WHERE guild_id=$1 AND planet_id=$2 AND controller='enemy'",
        guild_id, planet_id) or 0
    contested  = await conn.fetchval(
        "SELECT COUNT(*) FROM hexes "
        "WHERE guild_id=$1 AND planet_id=$2 AND status='contested'",
        guild_id, planet_id) or 0
    total_hexes = p_hexes + e_hexes

    state         = "🟢 ACTIVE" if is_active else "🔴 STANDBY"
    contract_name = cfg["contract_name"] if cfg and cfg["contract_name"] else "Unassigned"
    bot_name      = theme.get("bot_name", "WARBOT")
    pfac          = theme.get("player_faction", "PMC")
    efac          = theme.get("enemy_faction", "Enemy")
    tempo         = cfg["operational_tempo"] if cfg else 0
    tempo_cap     = cfg["tempo_threshold"] if cfg else 500
    tempo_bar     = _mini_bar(tempo, max_val=tempo_cap, length=10)
    fleets        = cfg["fleet_pool_available"] if cfg else 0

    p_bar_len   = int(12 * p_hexes / total_hexes) if total_hexes > 0 else 0
    e_bar_len   = 12 - p_bar_len
    sector_bar  = "█" * p_bar_len + "░" * e_bar_len

    embed = discord.Embed(
        title=f"{bot_name}  ·  Command Centre",
        description=(
            f"> {planet['name'] if planet else '—'}  ·  {state}  ·  Turn **{turn_count}**  ·  Every **{cfg['turn_interval_hours'] if cfg else '?'}h**\n"
            f"> Contract: **{contract_name}**  ·  Contractor: {planet['contractor'] if planet else '—'}  ·  Enemy: {planet['enemy_type'] if planet else '—'}"
        ),
        color=theme.get("color", 0xAA2222),
    )
    embed.add_field(name=f"🔵 {pfac}",   value=f"**{p_count}** units\n**{p_hexes}** sectors",  inline=True)
    embed.add_field(name=f"🔴 {efac}",   value=f"**{e_count}** units\n**{e_hexes}** sectors",  inline=True)
    embed.add_field(name="⚡ Contested", value=f"**{contested}** sector(s)",                    inline=True)
    embed.add_field(
        name=f"Sector Control  [{sector_bar}]",
        value=(
            f"{pfac}: **{p_hexes}**  ·  {efac}: **{e_hexes}**"
            if total_hexes > 0 else "*No sectors mapped yet.*"
        ),
        inline=False,
    )
    embed.add_field(
        name=f"Operational Tempo  `{tempo_bar}`  {tempo}/{tempo_cap}",
        value=f"**{fleets}** fleet(s) available",
        inline=False,
    )
    embed.set_footer(text=f"{theme.get('flavor_text', '')}  ·  Use the buttons below.")
    return embed


async def update_menu_embed(bot, guild_id: int, conn):
    cfg = await conn.fetchrow(
        "SELECT reg_channel_id, reg_message_id FROM guild_config WHERE guild_id=$1", guild_id)
    if not cfg or not cfg["reg_channel_id"] or not cfg["reg_message_id"]:
        return
    channel = bot.get_channel(cfg["reg_channel_id"])
    if not channel:
        return
    try:
        msg   = await channel.fetch_message(cfg["reg_message_id"])
        theme = await get_theme(conn, guild_id)
        embed = await build_menu_embed(guild_id, conn, theme)
        await msg.edit(embed=embed, view=MainMenuView(guild_id))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Menu embed update failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ENLISTMENT BOARD
# ══════════════════════════════════════════════════════════════════════════════

def _brigade_stats_line(stats: dict) -> str:
    return (
        f"ATK {stats['attack']:>2} | DEF {stats['defense']:>2} | "
        f"SPD {stats['speed']:>2} | MRL {stats['morale']:>2} | "
        f"SUP {stats['supply']:>2} | RCN {stats['recon']:>2}"
    )


def _build_brigade_dossier_embed(theme: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"Brigade Dossier  ·  {theme.get('bot_name', 'WARBOT')}",
        color=theme.get("color", 0xAA2222),
        description="Live registry — enlistment board and brigade info stay in sync.",
    )
    for data in BRIGADES.values():
        stats    = _brigade_stats_line(data["stats"])
        specials = "\n".join(f"· {text}" for text in data.get("specials", []))
        if not specials:
            specials = "· Standard line unit"
        embed.add_field(
            name=f"{data['emoji']}  {data['name']}",
            value=f"{data['description']}\n```{stats}```{specials}",
            inline=False)
    embed.set_footer(text="Use Enlist for new units · Use Deploy for returning rostered units.")
    return embed


def build_enlist_embed(theme: dict, planet_name: str, contractor: str,
                       enemy_type: str, commandant_count: int,
                       active_contracts: list, active_enemies: list,
                       contract_name: str = None, contract_status: str = None) -> discord.Embed:
    bot_name    = theme.get("bot_name", "WARBOT")
    color       = theme.get("color", 0xAA2222)
    status      = contract_status or "Standby"
    status_icon = "🟢" if status == "Active" else "🔴"

    embed = discord.Embed(
        title=f"{bot_name}  ·  Recruitment Centre",
        description=(
            f"> Planet: **{planet_name}**  ·  Contractor: **{contractor}**\n"
            f"> Enemy: **{enemy_type}**  ·  Status: {status_icon} **{status}**\n"
            f"> **{commandant_count}** commandant(s) on the roll"
        ),
        color=color,
    )

    # Active contracts
    if active_contracts:
        contract_lines = []
        for c in active_contracts[:5]:
            icon     = _status_icon(c["status"])
            diff     = _difficulty_icon(c.get("difficulty", "standard"))
            accepted = c.get("accepted_count", 0)
            cap      = c["deployment_capacity"] or 0
            dep      = c["deployed_units"] or 0
            contract_lines.append(
                f"{icon}{diff} **#{c['id']:03d} — {c['title']}**\n"
                f"  vs **{c['enemy']}**  ·  {accepted} enlisted  ·  {dep}/{cap} deployed"
            )
        embed.add_field(
            name="📋  Active Contracts",
            value="\n\n".join(contract_lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="📋  Active Contracts",
            value="*No contracts posted yet. Stand by for GM briefing.*",
            inline=False,
        )

    # Active enemy units
    if active_enemies:
        enemy_lines = []
        for e in active_enemies[:6]:
            hp  = e.get("hp", 100)
            bar = _mini_bar(hp, max_val=100, length=8)
            enemy_lines.append(f"🔴 **{e['unit_type']}** @ `{e['hex_address']}`  HP `{bar}` {hp}/100")
        embed.add_field(
            name="⚠️  Enemy Forces",
            value="\n".join(enemy_lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="⚠️  Enemy Forces",
            value="*No active enemy contact.*",
            inline=False,
        )

    embed.add_field(
        name="How to join",
        value=(
            "**⚔️ Enlist** — register as a commandant and create your unit\n"
            "**🚀 Deploy** — return a rostered unit to the active contract\n"
            "**📖 Brigade Info** — compare all brigade stats and specials"
        ),
        inline=False,
    )
    embed.set_footer(
        text=f"{theme.get('flavor_text', 'The contract must be fulfilled.')}  ·  Use /player_panel for your command file."
    )
    return embed


class _UnitNameModal(discord.ui.Modal, title="Name Your Unit"):
    unit_name = discord.ui.TextInput(
        label="Unit Name",
        placeholder="e.g. Iron Wolves",
        max_length=40,
        required=True,
    )

    def __init__(self, guild_id: int, returning: bool = False, contract_id: int = None):
        super().__init__()
        self.guild_id    = guild_id
        self.returning   = returning
        self.contract_id = contract_id

    async def on_submit(self, i: discord.Interaction):
        from cogs.squadron_cog import BrigadePickerView, brigade_picker_embed
        name  = str(self.unit_name).strip()
        embed = brigade_picker_embed(name, returning=self.returning)
        await i.response.send_message(
            embed=embed,
            view=BrigadePickerView(i.guild_id, name, self.contract_id),
            ephemeral=True)


class EnlistView(View):
    """Persistent view attached to the enlistment board message."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="⚔️ Enlist",      style=discord.ButtonStyle.success,   custom_id="enlist_board_enlist")
    async def enlist_now(self, i: discord.Interaction, b: Button):
        """
        Register the player as a commandant in the DB (creates commander_profiles row),
        then send the contract board so they can accept a contract and create their unit.
        """
        await i.response.defer(ephemeral=True, thinking=True)
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme = await get_theme(conn, i.guild_id)

            # Write commandant to DB
            from utils.profiles import ensure_commander_profile, grant_default_banner
            await ensure_commander_profile(conn, i.guild_id, i.user.id, i.user.display_name)
            await grant_default_banner(conn, i.guild_id, i.user.id)

            planet_id   = await get_active_planet_id(conn, i.guild_id)
            active_sq   = await conn.fetchrow(
                "SELECT name FROM squadrons "
                "WHERE guild_id=$1 AND planet_id=$2 AND owner_id=$3 AND is_active=TRUE LIMIT 1",
                i.guild_id, planet_id, i.user.id)
            rostered_sq = await conn.fetchrow(
                "SELECT name FROM squadrons "
                "WHERE guild_id=$1 AND owner_id=$2 ORDER BY id DESC LIMIT 1",
                i.guild_id, i.user.id)

            commandant_count = await conn.fetchval(
                "SELECT COUNT(*) FROM commander_profiles WHERE guild_id=$1", i.guild_id) or 0

            # Grant player role if configured
            cfg = await conn.fetchrow(
                "SELECT player_role_id FROM guild_config WHERE guild_id=$1", i.guild_id)
            if cfg and cfg["player_role_id"]:
                role = i.guild.get_role(cfg["player_role_id"])
                if role:
                    try:
                        await i.user.add_roles(role)
                    except discord.Forbidden:
                        pass

            rows = await fetch_board_contracts(conn, i.guild_id)

        if active_sq:
            await i.followup.send(
                f"✅ **{i.user.display_name}**, you are already deployed as **{active_sq['name']}**.\n"
                "Use **📋 Contract** on the command centre to check your contract status.",
                ephemeral=True)
            return

        if rostered_sq:
            await i.followup.send(
                f"✅ **{i.user.display_name}**, your commandant file is on record.\n"
                f"Your unit **{rostered_sq['name']}** is in reserve — use **🚀 Deploy** to redeploy it.",
                ephemeral=True)
            return

        confirm_embed = discord.Embed(
            title="⚔️  Commandant Registered",
            description=(
                f"Welcome to the roll, **{i.user.display_name}**.\n"
                f"**{commandant_count}** commandant(s) are now on record.\n\n"
                "Accept a contract below and name your unit to deploy."
            ),
            color=theme.get("color", 0xAA2222),
        )
        confirm_embed.set_footer(text=theme.get("flavor_text", "The contract must be fulfilled."))

        board_embed = build_contract_board_embed(theme, rows)
        await i.followup.send(embed=confirm_embed, ephemeral=True)
        await i.followup.send(
            embed=board_embed,
            view=ContractBoardView(i.guild_id, rows),
            ephemeral=True,
        )

    @discord.ui.button(label="🚀 Deploy",       style=discord.ButtonStyle.primary,   custom_id="enlist_board_deploy")
    async def deploy_now(self, i: discord.Interaction, b: Button):
        try:
            from cogs.squadron_cog import open_returning_deploy
            await open_returning_deploy(i)
        except Exception as e:
            try:
                if not i.response.is_done():
                    await i.response.send_message(f"❌ {e}", ephemeral=True)
                else:
                    await i.followup.send(f"❌ {e}", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="📖 Brigade Info", style=discord.ButtonStyle.secondary, custom_id="enlist_board_brigades")
    async def brigade_info(self, i: discord.Interaction, b: Button):
        try:
            theme = {"color": 0xAA2222, "bot_name": "WARBOT"}
            try:
                pool = await get_pool()
                async with pool.acquire() as conn:
                    theme = await get_theme(conn, i.guild_id)
            except Exception:
                pass
            embed = _build_brigade_dossier_embed(theme)
            await i.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"Error loading brigades: {e}", ephemeral=True)


async def refresh_enlist_counter(bot, guild_id: int, conn):
    """Update the persistent enlistment board with current theatre, contracts, and enemy data."""
    try:
        cfg = await conn.fetchrow(
            "SELECT enlist_channel_id, enlist_message_id, active_planet_id, contract_name "
            "FROM guild_config WHERE guild_id=$1", guild_id)
        is_active = await has_active_contracts(conn, guild_id)
        if not cfg or not cfg["enlist_channel_id"] or not cfg["enlist_message_id"]:
            return
        channel = bot.get_channel(cfg["enlist_channel_id"])
        if not channel:
            return
        msg       = await channel.fetch_message(cfg["enlist_message_id"])
        planet_id = cfg["active_planet_id"] or await get_active_planet_id(conn, guild_id)
        planet    = await conn.fetchrow(
            "SELECT name, contractor, enemy_type FROM planets WHERE guild_id=$1 AND id=$2",
            guild_id, planet_id)

        # Commandant count from profiles table (not just active squadrons)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM commander_profiles WHERE guild_id=$1", guild_id) or 0

        active_contracts = await fetch_board_contracts(conn, guild_id, limit=5)

        active_enemies = await conn.fetch(
            "SELECT unit_type, hex_address, hp FROM enemy_units "
            "WHERE guild_id=$1 AND planet_id=$2 AND is_active=TRUE ORDER BY id LIMIT 6",
            guild_id, planet_id)

        theme = await get_theme(conn, guild_id)
        embed = build_enlist_embed(
            theme,
            planet["name"]       if planet else "Unknown",
            planet["contractor"] if planet else "---",
            planet["enemy_type"] if planet else "---",
            count,
            list(active_contracts),
            list(active_enemies),
            cfg["contract_name"] if cfg and cfg["contract_name"] else "Unassigned",
            "Active" if is_active else "Standby",
        )
        await msg.edit(embed=embed, view=EnlistView(guild_id))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Enlist counter refresh failed: {e}")


async def refresh_contract_board(bot, guild_id: int, conn):
    """Update the persistent live contract board — markdown list only, no interactive buttons."""
    try:
        cfg = await conn.fetchrow(
            "SELECT contract_board_channel_id, contract_board_message_id "
            "FROM guild_config WHERE guild_id=$1", guild_id)
        if not cfg or not cfg["contract_board_channel_id"] or not cfg["contract_board_message_id"]:
            return
        channel = bot.get_channel(cfg["contract_board_channel_id"])
        if not channel:
            return
        msg   = await channel.fetch_message(cfg["contract_board_message_id"])
        theme = await get_theme(conn, guild_id)
        rows  = await fetch_board_contracts(conn, guild_id)

        planet_id      = await get_active_planet_id(conn, guild_id)
        active_enemies = await conn.fetch(
            "SELECT unit_type, hex_address, hp FROM enemy_units "
            "WHERE guild_id=$1 AND planet_id=$2 AND is_active=TRUE ORDER BY id LIMIT 8",
            guild_id, planet_id)

        embed = build_public_contract_board_embed(theme, rows, list(active_enemies))
        await msg.edit(embed=embed, view=None)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Contract board refresh failed: {e}")


async def refresh_public_panels(bot, guild_id: int, conn):
    """Refresh persistent public embeds that describe the current theatre."""
    await update_menu_embed(bot, guild_id, conn)
    await refresh_enlist_counter(bot, guild_id, conn)
    await refresh_contract_board(bot, guild_id, conn)