import discord
import asyncio

async def rotar_estado(bot):
    await bot.wait_until_ready()

    while not bot.is_closed():
        # Estado 1
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="developer: neiwito"
            )
        )
        await asyncio.sleep(15)

        # Estado 2
        await bot.change_presence(
            activity=discord.Game(name="San Martin RP")
        )
        await asyncio.sleep(15)
