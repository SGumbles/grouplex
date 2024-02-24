# Grouplex
A Discord bot for streaming movies from a Plex server.

## Installing
Ok hotshot, decrypt that secrets file with

`gpg -o secrets.json secrets.json.gpg`

IF you're cool enough to know the secret password. OTHERWISE, you'll need to make your own from `secrets.json.template` and fill out the keys and tokens.

### Getting your bots token
This is all done in the Discord developers control panel where you will register the bot and generate an invite URL. More info here : https://discordpy.readthedocs.io/en/stable/discord.html

The Plex token can be found following instructions here : https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/

## Setting up the bot and running it
Install all the dependencies with `pip install dependencies.txt` and then run it with `python bot/bot.py` and away you go. A great night of grouplex is right around the corner for you and your boys, no wives allowed.

You will need to ensure that the dependencies for Chromium are installed.

```console
goodhusband@NoWivesPC:~$ playwright install chromium
Browser Chromium installed...
You are a good husband and it's perfectly normal what you do with your friends.
goodhusband@NoWivesPC:~$
```

### Running inside WSL
You will need to do some fancy pants detective work to get the host IP address. This also applies if you're running the bot in a VM or something similar. 

From a WSL terminal do this
```console
goodhusband@NoWivesPC:~$ ip route list
default via 172.30.192.1 dev eth0 proto kernel
172.30.192.0/20 dev eth0 proto kernel scope link src 172.30.202.82
```
In this case, our external IP is `172.30.192.1` so our Plex host URL is `http://172.30.192.1:32400` or whatever port you have your Plex server bound to.