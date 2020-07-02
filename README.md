# SPARCbot
A Discord bot for vSPARC 2020.

## Contributing

@shardulc wants to eventually set this up such that pushing to `master` automatically deploys the updated bot to the server where it's running and it becomes live. So, meanwhile, it's a good idea to do all development work in other branches and merge via PR. Ask @shardulc if you want write access to this repository and also if you want access to a testing server where you can test experimental changes without fear.

## Getting started

1. Make sure you have Python 3.6+ installed, and then:
```
pip3 install -U google-api-python-client google-auth-httplib2 google-auth-oauthlib \
    oauth2client discord.py python-dateutil humanize
```

2. Clone this repository and in the same directory, make a file called `auth.json`
which is a JSON file with the following structure:
```json
{
    "discord_auth_token": "<obtained in step 3>",
    "google_api_auth": "<obtained in step 4>"
}
```
**Don't make this file public!** This file is in `.gitignore` to reduce the chances of pushing it to GitHub by accident.

3. Go to https://discord.com/developers/applications and make a new application.
   1. The "client secret" is what is stored in `auth.json`, under the key `discord_auth_token`.
   1. Go to "Bot" settings and make a bot account.
   1. Go to "OAuth2" settings and select the "bot" scope. Then, add the appropriate permissions: I think "Manage Roles", "View Channels", "Send Messages", "Embed Links", "Use External Emojis", and "Add Reactions" are needed right now. Then open the link that starts with `https://discord.com/api/oauth2/authorize` (right below the scopes box) and add the bot to a Discord server (ask @shardulc for access to a pre-existing testing server!).

4. (Remind @shardulc to fill this in later. You can leave it blank in `auth.json` for now.)

5. Remember to make a new branch if you are working on new features!

6. Run the bot with `python3 SPARCbot.py`.

## TODO

* Some functioning code already exists for a Google Calendar integration. Iron it out and make sure it does what people want it to do.
* Automatically keep track of bets! Will probably need a form of persistent storage that doesn't reset when the bot is restarted. Even better if this persistent storage is actually a Google Spreadsheet also accessible to humans.
* Checking whether roles exist on the server and whether a member has certain roles is a little befuddled right now, and there is code duplication / code is not well-organized. Come up with a better way to do this. Maybe using bot-, cog-, and command-level [checks](https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#discord.ext.commands.Bot.check).
* Add Easter eggs? Or rather, secular diet-inclusive surprises.
