from typing import Type
from discord.app_commands.tree import CommandTree
from discord.ext.commands.bot import _default
from plexapi.server import PlexServer
import json
import discord
from discord.ext import commands

import logging
logging.basicConfig(level=logging.DEBUG)

intents = discord.Intents.default()
discordClient = discord.Client(intents=intents)


class GrouPlexBot(commands.Bot):
	def __init__(self) -> None:
		intents = discord.Intents.default()
		super().__init__(command_prefix=commands.when_mentioned_or('$'),intents=intents)

		self.add_command(self.show_playlist)
		self.add_command(self.play)
		self.add_command(self.pause)
		self.add_command(self.call_nigel_gay)

	async def setup_hook(self):
		the_guild_id = discord.Object(id=SECRETS['test_guild_id'])
		# This copies the global commands over to your guild.
		self.tree.copy_global_to(guild=the_guild_id)
		await self.tree.sync()

	@commands.command()
	async def show_playlist(ctx,*args):
		pass

	@commands.command()
	async def play(ctx,*args):
		pass
	@commands.command()
	async def call_nigel_gay(ctx,*args):
		pass
	@commands.command()
	async def pause(ctx,*args):
		pass


# @discordClient.event
# async def on_ready():
# 	print("Aight fam, we logged in yo.")

# @discordClient.event
# async def on_message(message):
# 	if message.content.startswith("$hello"):
# 		await message.channel.send("Haaaay!")

try:
	import pathlib
	p = pathlib.Path(__file__).parent.joinpath('../secrets.json').resolve()
	with open(p) as f:
		SECRETS = json.load(f)
except:
	print(
		"""
		You need to have a secrets.json file in the root directory (or decrypt the SUPER SECRET one already in the repo).
		"""
	)
	exit()
bot = GrouPlexBot()
bot.run(SECRETS['discord_bot_key'])

# Get the stupid IP from `ip route list` if on WSL
# plex = PlexServer()
# print(plex.clients())