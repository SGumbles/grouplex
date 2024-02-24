from typing import Type, List, Optional
from plexapi.server import PlexServer
from plexapi.media import Media
import pathlib
import json
import discord
import re
import argparse
from discord import app_commands
from discord.ui import Select
from urllib.parse import parse_qs, urlsplit, urlunsplit

import asyncio
from playwright.async_api import async_playwright, Request, Playwright, Browser

import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3.connectionpool").setLevel('INFO')
logging.getLogger("asyncio").setLevel('INFO')
logger = logging.getLogger("GrouPlexBot")

############################
###
### CONFIG
###
############################
## Wait for this long to try and connect / dick around with Plex server connections
PLEX_TIMEOUT = 4

SECRETS = {}
SECRETS_JSON_FILE_PATH = pathlib.Path(__file__).parent.joinpath('../secrets.json').resolve()
FRIENDS = {}
FRIENDS_JSON_FILE_PATH = pathlib.Path(__file__).parent.joinpath('../cached_friends.json').resolve()

PLEX_SERVER_POOL = []
PLEX_CLIENT = None

if __name__=="__main__":
	parser = argparse.ArgumentParser(description="Runs a Discord bot so you and your boys can do FUN stuff without the wife knowing. Fun, normal")
	parser.add_argument("--force-friends-search", action="store_true")
	args = parser.parse_args()

try:
	with open(SECRETS_JSON_FILE_PATH) as f:
		SECRETS = json.load(f)
except:
	logger.critical("You need to have a secrets.json file in the root directory (or decrypt the SUPER SECRET one already in the repo).")
	exit()


############################
###
### PLEX INTERFACE
###
############################

def populate_friends():
	FRIENDS = {}
	async def pw_loop(pw: Playwright):
		browser = await pw.webkit.launch(headless=False)
		page = await browser.new_page()
		
		def pageCallback(req:Request):
			args = parse_qs(req.url)
			if 'X-Plex-Token' in args and re.search(r"(\d{1,3}-?){4}\.\w+\.plex\.direct:\d+",req.url):
				## Ok save this bad boy
				parts = urlsplit(req.url)
				url = urlunsplit( (parts[0],parts[1],*['']*3) ) #Note: *['']*3 is one less key-stroke than '','','' THEREFORE it is better
				token = args['X-Plex-Token'][0]
				if token not in FRIENDS:
					logger.info(f"Saving server token for {url} --- {token}")
				FRIENDS[token] = url
				
		page.on('request',pageCallback)
		browser_closed = False
		def close_browser(b:Browser):
			nonlocal browser_closed
			browser_closed = True
		browser.on("disconnected",close_browser)
		page.on('close',close_browser)
		await page.goto(SECRETS['plex_url'])
		## Wait for the user to close the browser
		while not browser_closed:
			await asyncio.sleep(1)
		await browser.close()
	async def run_browser():
		async with async_playwright() as pw:
			await pw_loop(pw)
	logger.info("*********************************************")
	logger.info("*\tRunning browser for sign-in")
	logger.info("*\tSign in to Plex, click around some libraries and then just close the window. Easy Peasy!")
	logger.info("*********************************************")
	asyncio.run(run_browser())
	with open(FRIENDS_JSON_FILE_PATH,'w') as f:
		json.dump(FRIENDS,f)

if args.force_friends_search:
	populate_friends()

try:
	with open(FRIENDS_JSON_FILE_PATH) as f:
		FRIENDS = json.load(f)
except:
	logger.warning("Can't find cached_friends.json, forcing sign-in...")
	populate_friends()
	exit()

logger.info("Creating Plex server pool")


for token, url in FRIENDS.items():
	logger.info(f"Connecting to {url} with token {token} and timeout {PLEX_TIMEOUT}")
	try:
		PLEX_SERVER_POOL.append(PlexServer(baseurl=url,token=token,timeout=PLEX_TIMEOUT))
	except Exception as e:
		logger.warning(f"Failed to connect to server : {e}")

def print_clients_and_exit():
	logger.fatal("Set 'plex_client_name' in secrets.json to one of the following:")
	for server in PLEX_SERVER_POOL:
		logger.fatal(f"From {server.friendlyName}:")
		for i,c in enumerate(server.clients()):
			logger.fatal(f"\t{i+1}. {c.title}")
	exit()


if not 'plex_client_name' in SECRETS:
	print_clients_and_exit()
	
for server in PLEX_SERVER_POOL:
	try:
		PLEX_CLIENT = server.client(SECRETS['plex_client_name'])
		if PLEX_CLIENT is not None:
			break
	except:
		pass

if PLEX_CLIENT is None:
	logger.fatal(f"Can't find client with name {SECRETS['plex_client_name']}")
	print_clients_and_exit()

async def coro_mega_search(media_name:str):
	search_threads = [ asyncio.to_thread(s.search,media_name) for s in PLEX_SERVER_POOL]
	results =  await asyncio.gather(*search_threads)
	# Flatten all the results
	hub_types = ['movie','episode']
	return [x for serv in results for x in serv if x.type in hub_types]
	
def mega_search(media_name:str):
	try:
		results = asyncio.run(coro_mega_search(media_name))
	except:
		logging.fatal("Search broked")
	## Process the results? Sort by resolution?
	return results



############################
###
### DISCORD INTERFACE
###
############################


# results = mega_search("Openheimer")
# exit()

MAIN_GUILD = discord.Object(id=SECRETS['main_guild_id'])
class GroupPlex(discord.Client):
	def __init__(self):
		intents = discord.Intents.default()
		super().__init__(intents=intents)
		self.tree = app_commands.CommandTree(self)
	async def setup_hook(self) -> None:
		self.tree.copy_global_to(guild=MAIN_GUILD)
		await self.tree.sync(guild=MAIN_GUILD)

gp = GroupPlex()

@gp.event
async def on_ready():
	print("------------------------------------------------")
	print(f"Bot running as {gp.user} (ID: {gp.user.id})")
	print("------------------------------------------------")

async def media_autocomplete(
	interaction: discord.Interaction,
	current: str,
) -> List[app_commands.Choice[str]]:
	res = await coro_mega_search(current)
	return [
		app_commands.Choice(name=i.title, value=i.title)
		for i in res
	]

def get_human_video_quality(media:Media):
	if media.height < 720:
		return "😒🥔"
	elif media.height < 1080:
		return "720🥀"
	elif media.height < 2160:
		return "1080🍌"
	else:
		return "4k🍆💦"


@gp.tree.command()
@app_commands.describe(media='Title of media')
@app_commands.describe(play_now='Add to the queue or play right now')
@app_commands.autocomplete(media=media_autocomplete)
async def play(interaction: discord.Interaction, media:str, play_now:bool):
	"""Play a movie or show, either adding it to the queue or playing it now"""
	res = await coro_mega_search(media)
	if len(res) > 1:
		options = [discord.SelectOption(label=f"{m.title} ({get_human_video_quality(m.media[0])} res.) on {m._server.friendlyName}",
					value=m.key,
					description=m.summary) 
			for m in res]
		select_menu = discord.ui.Select(placeholder="Select which media to play",options=options)
		await interaction.response.send_modal(select_menu)
		print("Aight we gon dun play dis")
		print(select_menu.values)

	if play_now:
		pass
	# results_server = plex_server.search(search_string)
	# results_library = plex_server.library.search(search_string)

	# print(results_server)
	# print(results_library)

	# hub_types = ['movie','episode']
	# results = list(filter(lambda x: x.type in hub_types, results))
	
	# await interaction.response.send_message(f"Hello captain faggot face, I mean {interaction.user.mention}")

gp.run(SECRETS['discord_bot_key'])
