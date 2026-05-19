import time
import discord

from discord.ext import commands
from discord import app_commands


class Ping(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_ping(self, send):
        start = time.perf_counter()

        await send("Pinging...")

        latency = self.bot.latency * 1000
        response = (time.perf_counter() - start) * 1000

        embed = discord.Embed(title = "🏓 Pong!")

        embed.add_field(name = "WebSocket", value = f"{latency:.2f} ms")
        embed.add_field(name = "Response", value = f"{response:.2f} ms")

        return embed

    @commands.command()
    async def ping(self, ctx):
        embed = await self.send_ping(ctx.send)
        await ctx.send(embed = embed)

    @app_commands.command(name = "ping", description = "查看延遲")
    async def ping_slash(self, interaction: discord.Interaction):
        embed = await self.send_ping(interaction.response.send_message)
        await interaction.followup.send(embed = embed)

async def setup(bot):
    await bot.add_cog(Ping(bot))