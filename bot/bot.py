from plexapi.server import PlexServer

import logging
logging.basicConfig(level=logging.DEBUG)

# Get the stupid IP from `ip route list` if on WSL
plex = PlexServer()
print(plex.clients())