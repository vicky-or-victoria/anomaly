"""
Map cog — /map, /map_overview, /gm_map, /map_update commands + auto-update helpers.

Multi-contract support
──────────────────────
When multiple contracts are active on different planets, each planet gets its own
live tactical map.  Per-planet message IDs are stored in the planet_map_messages
table (guild_id, planet_id) → (channel_id, message_id).

The single map_channel_id / map_message_id fields in guild_config still serve as
the *default* channel for map posts when no per-planet override exists.

The system overview already queries all planets and now also highlights which
planets have active contracts.
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_pool, ensure_guild, get_theme, get_active_planet_id

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Per-planet map message helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _active_contract_planet_ids(conn, guild_id: int) -> list:
    """Return planet_ids for all currently deployable/active contracts."""
    rows = await conn.fetch(
        "SELECT DISTINCT planet_id FROM contracts "
        "WHERE guild_id=$1 AND status IN ('active','deployable') AND planet_id IS NOT NULL",
        guild_id)
    return [r["planet_id"] for r in rows]


async def _get_planet_map_message(conn, guild_id: int, planet_id: int):
    """Return (channel_id, message_id) for a planet's stored live map, or (None, None)."""
    row = await conn.fetchrow(
        "SELECT channel_id, message_id FROM planet_map_messages "
        "WHERE guild_id=$1 AND planet_id=$2",
        guild_id, planet_id)
    return (row["channel_id"], row["message_id"]) if row else (None, None)


async def _save_planet_map_message(conn, guild_id: int, planet_id: int,
                                   channel_id: int, message_id: int):
    await conn.execute(
        "INSERT INTO planet_map_messages "
        "(guild_id, planet_id, channel_id, message_id, updated_at) "
        "VALUES ($1,$2,$3,$4,NOW()) "
        "ON CONFLICT (guild_id, planet_id) DO UPDATE "
        "SET channel_id=EXCLUDED.channel_id, message_id=EXCLUDED.message_id, "
        "    updated_at=NOW()",
        guild_id, planet_id, channel_id, message_id)


async def _render_and_post_planet_map(
    bot, guild_id: int, planet_id: int, channel_id: int,
    movement_arrows: list = None,
) -> bool:
    """
    Render the tactical map for one planet and edit-or-post it to channel_id.
    Stored message IDs in planet_map_messages allow in-place editing.
    Returns True on success.
    """
    from utils.map_render import render_map_for_guild

    pool = await get_pool()
    async with pool.acquire() as conn:
        theme = await get_theme(conn, guild_id)
        planet = await conn.fetchrow(
            "SELECT name FROM planets WHERE guild_id=$1 AND id=$2", guild_id, planet_id)
        planet_name = planet["name"] if planet else f"Planet {planet_id}"
        try:
            buf = await render_map_for_guild(
                guild_id, conn, planet_id=planet_id,
                movement_arrows=movement_arrows)
        except Exception as e:
            log.warning(f"Map render error guild={guild_id} planet={planet_id}: {e}")
            return False
        stored_chan, stored_msg = await _get_planet_map_message(conn, guild_id, planet_id)

    channel = bot.get_channel(channel_id)
    if not channel:
        return False

    f = discord.File(buf, filename="warmap.png")
    embed = discord.Embed(
        title=f"\U0001f5fa\ufe0f  {theme.get('bot_name','WARBOT')} \u2014 {planet_name}",
        color=theme.get("color", 0xAA2222))
    embed.set_image(url="attachment://warmap.png")
    embed.set_footer(text=theme.get("flavor_text", ""))

    try:
        if stored_msg and stored_chan == channel_id:
            try:
                msg = await channel.fetch_message(stored_msg)
                await msg.edit(embed=embed, attachments=[f])
                return True
            except (discord.NotFound, discord.HTTPException):
                pass  # message gone — post a new one

        new_msg = await channel.send(embed=embed, file=f)
        pool2 = await get_pool()
        async with pool2.acquire() as conn2:
            await _save_planet_map_message(
                conn2, guild_id, planet_id, channel_id, new_msg.id)
        return True
    except Exception as e:
        log.warning(f"Map post error guild={guild_id} planet={planet_id}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Cog
# ══════════════════════════════════════════════════════════════════════════════

class MapCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /map ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="map", description="Render the current tactical map.")
    async def map_cmd(self, interaction: discord.Interaction):
        await ensure_guild(interaction.guild_id)
        await interaction.response.defer(thinking=True)
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme     = await get_theme(conn, interaction.guild_id)
            planet_id = await get_active_planet_id(conn, interaction.guild_id)
            planet    = await conn.fetchrow(
                "SELECT name FROM planets WHERE guild_id=$1 AND id=$2",
                interaction.guild_id, planet_id)
            try:
                from utils.map_render import render_map_for_guild
                buf = await render_map_for_guild(
                    interaction.guild_id, conn, planet_id=planet_id)
            except Exception as e:
                await interaction.followup.send(f"\u274c Map render failed: {e}")
                return
        planet_name = planet["name"] if planet else "Unknown"
        f = discord.File(buf, filename="warmap.png")
        embed = discord.Embed(
            title=f"\U0001f5fa\ufe0f {theme.get('bot_name','WARBOT')} \u2014 {planet_name}",
            color=theme.get("color", 0xAA2222))
        embed.set_image(url="attachment://warmap.png")
        embed.set_footer(text=theme.get("flavor_text",""))
        await interaction.followup.send(embed=embed, file=f)

    # ── /map_overview ─────────────────────────────────────────────────────────

    @app_commands.command(name="map_overview",
                          description="Show the planetary system overview (all planets).")
    async def map_overview(self, interaction: discord.Interaction):
        await ensure_guild(interaction.guild_id)
        await interaction.response.defer(thinking=True)
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme = await get_theme(conn, interaction.guild_id)
            try:
                from utils.map_render import render_overview_for_guild
                buf = await render_overview_for_guild(interaction.guild_id, conn)
            except Exception as e:
                await interaction.followup.send(f"\u274c Overview render failed: {e}")
                return
        f = discord.File(buf, filename="overview.png")
        embed = discord.Embed(
            title=f"\U0001fa90 {theme.get('bot_name','WARBOT')} \u2014 Planetary Theatres",
            color=theme.get("color", 0xAA2222))
        embed.set_image(url="attachment://overview.png")
        await interaction.followup.send(embed=embed, file=f)

    # ── /map_update ───────────────────────────────────────────────────────────

    @app_commands.command(name="map_update",
                          description="[Admin] Force-refresh all live map embeds.")
    async def map_update(self, interaction: discord.Interaction):
        await ensure_guild(interaction.guild_id)
        await interaction.response.defer(ephemeral=True, thinking=True)
        map_count = await auto_update_map(self.bot, interaction.guild_id)
        over_ok   = await auto_update_overview(self.bot, interaction.guild_id)
        msgs = []
        if map_count: msgs.append(f"\u2705 Tactical map(s) updated ({map_count} planet(s)).")
        if over_ok:   msgs.append("\u2705 Planetary system overview updated.")
        if not msgs:  msgs.append("\u274c No map channels configured.")
        await interaction.followup.send("\n".join(msgs), ephemeral=True)

    # ── /gm_map ───────────────────────────────────────────────────────────────

    @app_commands.command(name="gm_map",
                          description="[GM] Full GM map with all unit positions revealed.")
    @app_commands.describe(planet="Planet name to view (defaults to active planet)")
    async def gm_map_cmd(self, interaction: discord.Interaction, planet: str = None):
        from cogs.admin_cog import _is_admin, _is_gm
        await ensure_guild(interaction.guild_id)
        if not (await _is_admin(self.bot, interaction) or await _is_gm(interaction)):
            await interaction.response.send_message(
                "\U0001f6ab This command is restricted to GMs and Admins.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        pool = await get_pool()
        async with pool.acquire() as conn:
            theme = await get_theme(conn, interaction.guild_id)
            if planet:
                row = await conn.fetchrow(
                    "SELECT id FROM planets WHERE guild_id=$1 AND LOWER(name)=LOWER($2)",
                    interaction.guild_id, planet.strip())
                planet_id = row["id"] if row else await get_active_planet_id(
                    conn, interaction.guild_id)
            else:
                planet_id = await get_active_planet_id(conn, interaction.guild_id)
            planet_row  = await conn.fetchrow(
                "SELECT name FROM planets WHERE guild_id=$1 AND id=$2",
                interaction.guild_id, planet_id)
            planet_name = planet_row["name"] if planet_row else f"Planet {planet_id}"
            try:
                from utils.map_render import render_gm_map_for_guild
                buf = await render_gm_map_for_guild(
                    interaction.guild_id, conn, planet_id=planet_id)
            except Exception as e:
                await interaction.followup.send(
                    f"\u274c GM map render failed: {e}", ephemeral=True)
                return
        f = discord.File(buf, filename="gm_map.png")
        embed = discord.Embed(
            title=f"\U0001f5fa\ufe0f {theme.get('bot_name','WARBOT')} \u2014 GM Map: {planet_name}",
            description=(
                "**Fog of war lifted.** All player and enemy units shown.\n"
                "\U0001f535 Blue labels = player units  \u00b7  \U0001f534 Red labels = enemy units"
            ),
            color=0x2ECC71)
        embed.set_image(url="attachment://gm_map.png")
        embed.set_footer(text="GM eyes only \u2014 ephemeral.")
        await interaction.followup.send(embed=embed, file=f, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
# Auto-update helpers  (called by turn engine + admin cog)
# ══════════════════════════════════════════════════════════════════════════════

async def auto_update_map(bot, guild_id: int, movement_arrows: list = None) -> int:
    """
    Post or edit live tactical maps for all planets with active contracts.
    Falls back to the configured active planet if no contracts carry a planet_id yet
    (handles guilds that pre-date the planet_id column on contracts).

    Returns the number of planets whose map was successfully updated.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        cfg = await conn.fetchrow(
            "SELECT map_channel_id FROM guild_config WHERE guild_id=$1", guild_id)
        if not cfg or not cfg["map_channel_id"]:
            return 0
        channel_id     = cfg["map_channel_id"]
        active_planets = await _active_contract_planet_ids(conn, guild_id)
        if not active_planets:
            # Fallback: render the configured active planet (covers pre-contract-era and standby)
            active_planets = [await get_active_planet_id(conn, guild_id)]

    updated = 0
    for pid in active_planets:
        ok = await _render_and_post_planet_map(
            bot, guild_id, pid, channel_id,
            movement_arrows=movement_arrows)
        if ok:
            updated += 1
    return updated


async def auto_update_overview(bot, guild_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cfg = await conn.fetchrow(
            "SELECT overview_channel_id, overview_message_id FROM guild_config WHERE guild_id=$1",
            guild_id)
        if not cfg or not cfg["overview_channel_id"]:
            return False
        theme = await get_theme(conn, guild_id)
        try:
            from utils.map_render import render_overview_for_guild
            buf = await render_overview_for_guild(guild_id, conn)
        except Exception as e:
            log.warning(f"Overview render error guild={guild_id}: {e}")
            return False

    channel = bot.get_channel(cfg["overview_channel_id"])
    if not channel:
        return False

    f = discord.File(buf, filename="overview.png")
    embed = discord.Embed(
        title=f"\U0001fa90 {theme.get('bot_name','WARBOT')} \u2014 Planetary Theatres",
        color=theme.get("color", 0xAA2222))
    embed.set_image(url="attachment://overview.png")

    try:
        if cfg["overview_message_id"]:
            try:
                msg = await channel.fetch_message(cfg["overview_message_id"])
                await msg.edit(embed=embed, attachments=[f])
                return True
            except Exception:
                pass
        new_msg = await channel.send(embed=embed, file=f)
        pool2 = await get_pool()
        async with pool2.acquire() as conn2:
            await conn2.execute(
                "UPDATE guild_config SET overview_message_id=$1 WHERE guild_id=$2",
                new_msg.id, guild_id)
        return True
    except Exception as e:
        log.warning(f"Overview post error guild={guild_id}: {e}")
        return False


async def setup(bot):
    await bot.add_cog(MapCog(bot))