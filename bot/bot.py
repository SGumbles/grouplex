from typing import Type, List, Optional
from plexapi.server import PlexServer
from plexapi.media import Media
from plexapi.client import PlexClient
import pathlib
import json
import discord
import re
import argparse
import datetime
from discord import app_commands, User
from discord.ext import commands
from urllib.parse import parse_qs, urlsplit, urlunsplit
from table2ascii import table2ascii, PresetStyle

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
PLEX_CLIENT:PlexClient = None

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
	results =  await asyncio.gather(*search_threads, return_exceptions=False)
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
class GroupPlex(commands.Bot):
	class QueueEntry():
		def __init__(self,media:Media,interaction:discord.Interaction) -> None:
			self.media:Media = media
			self.user:User = interaction.user
			self.added:datetime.datetime = datetime.datetime.now()

	def __init__(self):
		self._should_run_play_queue = True
		self._currently_playing:Media = None
		self._queue:List[Media] = list()
		intents = discord.Intents.default()
		super().__init__(command_prefix=commands.when_mentioned_or('$'),intents=intents)
	
	async def setup_hook(self) -> None:
		self.tree.copy_global_to(guild=MAIN_GUILD)
		await self.tree.sync(guild=MAIN_GUILD)

	async def on_ready(self):
		print("------------------------------------------------")
		print(f"Bot running as {gp.user} (ID: {gp.user.id})")
		print("------------------------------------------------")
		# self.get_guild(MAIN_GUILD.id)
		self._main_channel = self.get_guild(int(MAIN_GUILD.id)).system_channel
		asyncio.run_coroutine_threadsafe(self.run_play_queue(),asyncio.get_event_loop())
	
	def is_playing_media(self):
		if PLEX_CLIENT.isPlayingMedia() is False:
			## Plex does this stupid thing where nothing will be playing but it says it's 'paused'
			if PLEX_CLIENT.timeline.state == 'paused' and self._currently_playing is None:
				return False
			else:
				return True
		else:
			return True

	async def run_play_queue(self):
		while(self._should_run_play_queue):
			await asyncio.sleep(20)
			if self.is_playing_media() is False:
				await self.play_next_in_queue()

	async def play_next_in_queue(self):
		if len(self._queue) > 0:
			## Play the next item in the queue
			entry = self._queue.pop(0)
			await self.message_main_channel(f"Ok, let's start the next reel! We got {entry.media.title} coming up next!")
			await self.play_or_queue(entry.media,True)
		else:
			## Play an informative documentary
			results = await coro_mega_search("Buck Breaking")
			await self.play_or_queue(results[0],True)
			await self.message_main_channel(f"Alright young bucks, we gonna play something from the archives to educationalize those who may not be melanized.👨🏿‍🎓✊🏿. Enjoy :deer:")

	async def message_main_channel(self,message:str,**kwargs):
		await self._main_channel.send(message,**kwargs)

	async def play_or_queue(self,media:Media,play_now:bool,interaction:discord.Interaction=None):
		if play_now:
			self._currently_playing = media
			PLEX_CLIENT.playMedia(media)
		else:
			self._queue.append(GroupPlex.QueueEntry(media,interaction))

	def get_currently_playing(self):
		return self._currently_playing

	def pause(self):
		PLEX_CLIENT.pause()

	def unpause(self):
		PLEX_CLIENT.play()

	def fastforward(self, seconds:int = 30):
		PLEX_CLIENT.seekTo( PLEX_CLIENT.timeline.time + (seconds * 1000))

	def rewind(self, seconds:int = 30):
		PLEX_CLIENT.seekTo( PLEX_CLIENT.timeline.time - (seconds * 1000))

	def remove_queue_idx(self,index_list:list):
		new_q = [x for idx,x in enumerate(self._queue,start=1) if idx not in index_list]
		self._queue = new_q

	def move_queue_idx(self,from_number, to_number):
		self._queue.insert(to_number-1,self._queue.pop(from_number-1))

	def get_queue_str(self):
		body_rows = []
		col_widths = [5,55,20,20]
		for idx, q in enumerate(self._queue,start=1):
			body_rows.append([str(idx)[:col_widths[0]], q.media.title[:col_widths[1]], q.media._server.friendlyName[:col_widths[2]], q.user.name[:col_widths[3]]])
		table_str = table2ascii(header=["#","Title","Server","Added By"],
					body=body_rows,
					column_widths=col_widths,
					style=PresetStyle.ascii_box
		)
		return f"```{table_str}```"

gp = GroupPlex()

############################
###
### PLAY COMMAND
###
############################


## You can't just pass a callback or compose a Select object, you need to sub-class and override the callback function like it's fucking 1999
class HolyShitDiscordPyIsFuckingTerrible(discord.ui.Select):
	def __init__(self, media_list, play_now:bool):
		self._media_list = media_list
		self._play_now = play_now
		# Adds the dropdown to our view object.
		options = [discord.SelectOption(label=f"{m.title} ({HolyShitDiscordPyIsFuckingTerrible.get_human_video_quality(m.media[0])}) on {m._server.friendlyName}",
					value=m.key,
					description=m.summary[:100]) # This is limited to 100 characters and will BREAK if you give more. Thanks.
			for m in media_list]
		super().__init__(placeholder="Which one do you want to play chief?",options=options)
	
	@classmethod
	def get_human_video_quality(cls,media:Media):
		if media.height < 720:
			return "😒🥔"
		elif media.height < 1080:
			return "720🥀"
		elif media.height < 2160:
			return "1080🍌"
		else:
			return "4k🍆💦"
		
	@classmethod
	def format_media(cls,m:Media):
		if m.type == 'movie':
			return f"{m.title} ({m.year}) - {m.tagline}"
		elif m.type == 'episode':
			return f"{m.title} ({m.grandparentTitle}) - {m.summary}"
		
	async def callback(self, interaction: discord.Interaction):
		for m in self._media_list:
			if m.key == self.values[0]:
				if self._play_now:
					await interaction.response.send_message(f"Alright brothers, {interaction.user} has asked we play {m.title}.")
				else:
					await interaction.response.send_message(f"Alright brothers, {interaction.user} has added {m.title} to the queue.")
				await gp.play_or_queue(m,self._play_now,interaction)
				break

class MediaSelectView(discord.ui.View):
	def __init__(self, media_list, play_now:bool):
		super().__init__()
		self.add_item(HolyShitDiscordPyIsFuckingTerrible(media_list,play_now))

async def media_autocomplete(
	interaction: discord.Interaction,
	current: str,
) -> List[app_commands.Choice[str]]:
	res = await coro_mega_search(current)
	uniq = {m.guid:m for m in res}
	return [
		app_commands.Choice(name=HolyShitDiscordPyIsFuckingTerrible.format_media(i)[:100], value=f"{i.title}:::{i.guid}")
		for i in uniq.values()
	]

@gp.tree.command()
@app_commands.describe(media='Title of media')
@app_commands.describe(play_now='Add to the queue or play right now')
@app_commands.autocomplete(media=media_autocomplete)
async def play(interaction: discord.Interaction, media:str, play_now:bool=False):
	"""Play a movie or show, either adding it to the queue or playing it immediately"""
	## What the fuck is happening with discord.py?
	context = await commands.Context.from_interaction(interaction)
	guid = None
	if match := re.match(r'(.+):::(.+)',media):
		media = match[1]
		guid = match[2]
		res = await coro_mega_search(media)
		res = [x for x in res if x.guid == guid]
	else:
		res = await coro_mega_search(media)
	if len(res) > 1:
		await context.send(view=MediaSelectView(res,play_now),ephemeral=True)
	else:
		if play_now:
			await interaction.response.send_message(f"Alright brothers, {interaction.user} has asked we play {res[0].title}.")
		else:
			await interaction.response.send_message(f"Alright brothers, {interaction.user} has added {res[0].title} to the queue.")
		await gp.play_or_queue(res[0],play_now,interaction)

############################
###
### QUEUE COMMAND
###
############################

@gp.tree.command()
async def show_queue(interaction: discord.Interaction):
	"""Shows the play queue"""
	context = await commands.Context.from_interaction(interaction)
	await context.send(gp.get_queue_str(),ephemeral=True)

@gp.tree.command()
@app_commands.describe(item_number='Which queue entry to remove. Use /show_queue to list entries. This can be a list of numbers separated by spaces.')
async def trim_queue(interaction: discord.Interaction, item_number:str):
	"""Remove items from the play queue"""
	context = await commands.Context.from_interaction(interaction)
	try:
		gp.remove_queue_idx([int(x) for x in item_number.split(' ')])
	except:
		await context.send("You goofed something up buddy, try again",ephemeral=True)
	else:
		await context.send(gp.get_queue_str(),ephemeral=True)

@gp.tree.command()
@app_commands.describe(from_number='Queue item to move')
@app_commands.describe(to_number='The new spot in the queue. So 1 would be at the top for example')
async def move_queue(interaction: discord.Interaction, from_number:app_commands.Range[int,1], to_number:app_commands.Range[int,1]):
	"""Move a queue item from one spot to another"""
	context = await commands.Context.from_interaction(interaction)
	try:
		gp.move_queue_idx(from_number, to_number)
	except:
		await context.send("You goofed something up buddy, try again",ephemeral=True)
	else:
		await context.send(gp.get_queue_str(),ephemeral=True)


############################
###
### PLAYBACK COMMAND
###
############################

@gp.tree.command()
async def next(interaction: discord.Interaction):
	"""Play the next item in the queue"""
	context = await commands.Context.from_interaction(interaction)
	await gp.play_next_in_queue()
	await context.send("Got it! Playing next in queue",ephemeral=True)

@gp.tree.command()
async def pause(interaction: discord.Interaction):
	"""Pause the playing item"""
	context = await commands.Context.from_interaction(interaction)
	gp.pause()
	await context.send("Ok! We'll wait for ya.",ephemeral=True)

@gp.tree.command()
async def resume(interaction: discord.Interaction):
	"""Resume a paused playback"""
	context = await commands.Context.from_interaction(interaction)
	gp.unpause()
	await context.send("Right! Playing again.",ephemeral=True)

@gp.tree.command()
async def fast_forward(interaction: discord.Interaction, seconds:int = 30):
	"""Fast forward"""
	context = await commands.Context.from_interaction(interaction)
	gp.fastforward(seconds)
	await context.send("Gotcha! Zippin' ahead for ya buddy!",ephemeral=True)

@gp.tree.command()
async def rewind(interaction: discord.Interaction, seconds:int = 30):
	"""Rewind"""
	context = await commands.Context.from_interaction(interaction)
	gp.rewind(seconds)
	await context.send("Whoa there! Backing it up for ya.",ephemeral=True)

@gp.tree.command()
async def whats_playing(interaction: discord.Interaction):
	"""Shows info on what's currently playing"""
	context = await commands.Context.from_interaction(interaction)
	m = gp.get_currently_playing()
	if m is None:
		await context.send(f"Nothing is playing right now! Queue something up for the fellas!",ephemeral=True)
	else:
		info=f"{m.title} ({m.year})\n\n{m.summary}"
		await context.send(f"Oh, it's really good! The guys are loving it, it's... \n\n{info}",ephemeral=True)

gp.run(SECRETS['discord_bot_key'])
