from plexapi.server import PlexServer
import json
import discord

import logging
logging.basicConfig(level=logging.DEBUG)

intents = discord.Intents.default()
discordClient = discord.Client(intents=intents)

@discordClient.event
async def on_ready():
	print("Aight fam, we logged in yo.")

@discordClient.event
async def on_message(message):
	if message.content.startswith("$hello"):
		await message.channel.send("Haaaay!")

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
discordClient.run(SECRETS['discord_bot_key'])

# Get the stupid IP from `ip route list` if on WSL
# plex = PlexServer()
# print(plex.clients())