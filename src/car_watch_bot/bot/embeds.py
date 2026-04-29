"""Discord embed builders."""

import discord

from car_watch_bot.core.models import DigestListing


def build_listing_embed(
    listing: DigestListing,
    heading: str | None = None,
    query: str | None = None,
) -> discord.Embed:
    """Build a Discord embed for one listing."""

    embed = discord.Embed(
        title=listing.title[:256],
        url=listing.url,
        color=discord.Color.blue(),
    )
    if heading or query:
        description_lines = []
        if heading:
            description_lines.append(heading)
        if query:
            description_lines.append(f"Query: {query}")
        embed.description = "\n".join(description_lines)

    embed.add_field(name="Source", value=listing.source_name, inline=True)
    embed.add_field(name="Price", value=listing.converted_price, inline=True)
    embed.add_field(name="Original price", value=listing.original_price, inline=True)
    embed.add_field(name="Mileage", value=listing.converted_mileage, inline=True)
    embed.add_field(name="Original mileage", value=listing.original_mileage, inline=True)
    embed.add_field(
        name="Score reasons",
        value=", ".join(listing.score_reasons)[:1024] or "none",
        inline=False,
    )
    return embed
