from asyncio import get_event_loop, sleep, TimeoutError
import datetime
from dateutil.parser import parse as parse_datetime
from enum import Enum
from humanize import naturalday, naturaltime
import json
import logging
from os.path import exists as file_exists
import pickle
from random import randint
import csv
import json
from tabulate import tabulate

import discord
from discord.ext import commands

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

logging.basicConfig(level=logging.INFO)

CONFIG_FILE = 'main_config.json'
with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)
with open(config['auth_file'], 'r') as f:
    config.update(json.load(f))
bot = commands.Bot(config['command_prefix'])

seens = {}

# helper functions

async def timed_send(ctx, msg):
    #async with ctx.channel.typing():
    #    await sleep(len(msg) * 0.06) # 0.06 seconds to 'type' each character
    return await ctx.send(msg)

async def check_guild_role(ctx, role, warn=False):
    if not ctx.guild:
        await timed_send(ctx, config['error_messages']['no_DM'])
        return None
    role_inst = discord.utils.get(ctx.guild.roles, name=role)
    if not role_inst:
        await timed_send(ctx, config['error_messages']['role_not_found'].format(role))
        return None
    if warn and role_inst not in ctx.author.roles:
        await timed_send(ctx, config['error_messages']['need_role'].format(role))
    return role_inst in ctx.author.roles

async def asyncify(fun):
    return await get_event_loop().run_in_executor(None, fun)

def time_format(dt):
    return dt.isoformat() + 'Z'

async def get_nick_from_id(ctx,id):
    try:
        if not ctx.guild:
            await timed_send(ctx, config['error_messages']['no_DM'])
            return None
        member = ctx.guild.get_member(id)
        if member:
            if member.nick:
                return member.nick
            user = await bot.fetch_user(id)
            return user.name
        return "Unknown"
    except Exception:
        raise

class Welcome(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.lock = False

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        global seens
        if before.status is discord.Status.online and after.status is not discord.Status.online:
            # member might be exiting vSPARC for now
            seens[before.id] = datetime.datetime.now()
        elif before.status is not discord.Status.online and after.status is discord.Status.online:
            # member might be entering vSPARC
            seen = seens.get(before.id, datetime.datetime(2020, 6, 1))
            if datetime.datetime.now() - seen > datetime.timedelta(hours=config['timeouts']['away_hours']):
                # yup, member has not been seen online in the last hour
                roles_list = after.guild.roles
                if discord.utils.get(roles_list, name=config['everything_role']) not in after.roles:
                    await before.remove_roles(*list(filter(
                        lambda r: r.name in [x['role'] for x in config['categories'].values()],
                        roles_list)))
                novice_role = discord.utils.get(roles_list, name=config['novice_role'])
                if novice_role and roles_list.index(after.top_role) < roles_list.index(novice_role):
                    # member is still in novice mode so make sure they have the novice role
                    await after.add_roles(novice_role)

    @commands.command()
    async def tutorial(self, ctx):
        if self.lock:
            await timed_send(ctx, 'one at a time, please!')
            return
        self.lock = True
        for msg in [
            'let\'s get started!',
            'SPARC is organized into four different zones.',
            'I\'ll walk you through them one by one, and when you\'re done checking '
                'each one out and want to move on, just react 👍 to my message.'
        ]:
            await timed_send(ctx, msg)

        def check(messages, reaction, user):
            return reaction.message.id in map(lambda m: m.id, messages) and user == ctx.message.author and str(reaction.emoji) == '👍'

        roles_list = ctx.guild.roles
        for cat in config['categories']:
            sent = [
                await timed_send(ctx, 'the {0} zone: {1}'.format(config['categories'][cat]['noun'], config['categories'][cat]['description'])),
                await timed_send(ctx, config['categories'][cat]['tutorial'].format(config['categories'][cat]['role']))
            ]
            await ctx.author.add_roles(discord.utils.get(roles_list, name=config['categories'][cat]['role']))

            try:
                await self.bot.wait_for('reaction_add', timeout=config['timeouts']['tutorial_react_seconds'], check=lambda r, u: check(sent, r, u))
            except TimeoutError:
                sent = [await timed_send(ctx, '{}, are you still here? react 👍 if you are'.format(ctx.author.mention))]
                try:
                    await self.bot.wait_for('reaction_add', timeout=config['timeouts']['tutorial_cancel_seconds'], check=lambda r, u: check(sent, r, u))
                except TimeoutError:
                    await timed_send(ctx, 'guess not :/')
                    self.lock = False
                    return

            await ctx.author.remove_roles(*list(filter(
                lambda r: r.name in [x['role'] for x in config['categories'].values()],
                roles_list)))

        self.lock = False
        await timed_send(ctx, 'congratulations! you have completed the tutorial.')
        await ctx.author.add_roles(discord.utils.get(roles_list, name=config['student_role']))
        await ctx.author.remove_roles(discord.utils.get(roles_list, name=config['novice_role']))
        await timed_send(ctx, 'try pinging me with "$hello"')

    @commands.command()
    async def hello(self, ctx):
        is_novice = await check_guild_role(ctx, config['novice_role'])
        if is_novice is None:
            return
        elif is_novice:
            await timed_send(ctx, 'hi {}! welcome to SPARC'.format(ctx.author.mention))
            await timed_send(ctx, 'I\'m SPARCbot and I can show you around. type "$tutorial" to begin.')
        else:
            await timed_send(ctx, 'hi {}! what do you want to do today?'.format(ctx.author.mention))
            await timed_send(ctx, 'respond with one option: $iwantto [{}]'.format('|'.join(config['categories'].keys())))
            await timed_send(ctx, 'or respond with $unsure')

    @commands.command()
    async def iwantto(self, ctx, role: str):
        is_novice = await check_guild_role(ctx, config['novice_role'])
        if is_novice is None:
            return
        cat_role = None
        if role in config['categories']:
            cat_role = discord.utils.get(ctx.guild.roles, name=config['categories'][role]['role'])
        if cat_role is None:
            await timed_send(ctx, config['error_messages']['role_not_found'].format(role))
            return
        await ctx.author.add_roles(cat_role)
        if is_novice:
            await timed_send(ctx, 'welcome to the {} zone!'.format(config['categories'][role]['noun']))
            await timed_send(ctx, config['categories'][role]['description'])
        else:
            await sleep(0.5)
            await ctx.message.add_reaction('👍')
            r = randint(1, 4)
            if r == 1:
                await timed_send(ctx, 'protip: did you know you can add roles to yourself by clicking on your name?')
            elif r == 2:
                await timed_send(ctx, 'protip: if you give yourself the "everything" role, you\'ll see all the categories all the time, and I\'ll never take it away from you <3')

    @commands.command()
    async def unsure(self, ctx):
        await timed_send(ctx, 'I\'m afraid I can\'t let you do that.')

class Bets(commands.Cog):


    def __init__(self,bot):
        self.bot = bot
        self.lock = False

    def add_new_bet(self,name,statement,status='open'):
        #add a new bet
        with open("bet_log.json", "r") as read_file:
            bet_log = json.load(read_file)
        current_bet_id = bet_log['current_bet_id'] + 1
        bet_key = 'bet_'+str(current_bet_id)

        #make the new bet
        new_bet = {
            "bet_id": current_bet_id,
            "bidder": name,
            "status": config['bet_status'][status],
            "statement": statement
        }
        bet_log[bet_key] = new_bet

        #update current_bet_id
        bet_log['current_bet_id'] = current_bet_id

        with open("bet_log.json","w") as write_file:
            json.dump(bet_log,write_file,indent=4)
        return current_bet_id

    def check_author(self,ctx,bet_id):
        with open("bet_log.json", "r") as read_file:
            bet_log = json.load(read_file)
        bet_key = 'bet_'+str(bet_id)
        try:
            if bet_log[bet_key]['bidder'] == ctx.author.id or bet_log[bet_key]['seller'] == ctx.author.id:
                return True
            else:
                return False
        except Exception as e:
            pass
        return bet_log[bet_key]['bidder'] == ctx.author.id

    @commands.command()
    async def bet(self,ctx,*,statement):
        '''<statement>: create an open bet'''
        #share a unique bet_id
        try:
            bet_id = self.add_new_bet(ctx.author.id,statement)
            nick = await get_nick_from_id(ctx,ctx.author.id)
            await timed_send(ctx, 'added bet '+str(bet_id)+' \"'+statement+'\" by '+nick+' to log.')
        except Exception as e:
            raise
            #await timed_send(ctx, 'Hmm...that didn\'t seem to work.')

    @commands.command()
    async def imout(self,ctx):
        '''Cancels your most recent unclaimed offer'''
        if self.lock:
            await timed_send(ctx, 'still working!')
            return
        self.lock = True


        with open("bet_log.json", "r") as read_file:
            bet_log = json.load(read_file)
        current_bet_id = bet_log['current_bet_id']

        for i in range(current_bet_id,0,-1):
            bet_key = 'bet_'+str(i)
            try:
                if bet_log[bet_key]['bidder'] == ctx.author.id and bet_log[bet_key]['status'] in (config['bet_status']['open'],config['bet_status']['standing']):
                    removed = bet_log.pop(bet_key)
                    with open("bet_log.json","w") as write_file:
                        json.dump(bet_log,write_file,indent=4)
                    nick = await get_nick_from_id(ctx,ctx.author.id)
                    await timed_send(ctx,'removed '+bet_key+' by '+nick)
                    self.lock = False
                    return
            except KeyError as e:
                pass
        await timed_send(ctx, 'I couldn\'t find any of your open bets')

    @commands.command()
    async def viewbets(self,ctx,view:int = 10,status:str = None):
        '''[num_bets] [status]: See open, pending, resolved or all bets'''
        with open("bet_log.json", "r") as read_file:
            bet_log = json.load(read_file)
        current_bet_id = bet_log['current_bet_id']
        bet_rows = []
        try:
            await timed_send(ctx,'Viewing latest '+str(view)+' bets with status ' + (status if status else 'anything'))
            while len(bet_rows) <= view and current_bet_id > 0:
                bet_key = 'bet_'+str(current_bet_id)
                if bet_key in bet_log:
                    if bet_log[bet_key]['status'] == status or not status:
                        bet_row = []
                        for cname in config['bet_log_columns']:
                            bet_row = bet_row+[("N/A" if cname not in bet_log[bet_key] else bet_log[bet_key][cname] if isinstance(bet_log[bet_key][cname],str) else str(bet_log[bet_key][cname]) if cname == 'bet_id' else await get_nick_from_id(ctx,bet_log[bet_key][cname]))]
                        bet_rows.append(bet_row)
                current_bet_id = current_bet_id - 1
            await timed_send(ctx, '`'+tabulate(bet_rows,headers=config['bet_log_columns'])+'`')
        except Exception as e:
            raise

        # TODO: open
        # TODO: view limit
        # TODO: pending
        # TODO: resolved

    @commands.command()
    async def take(self,ctx,bet_id: int):
        '''<bet_id>: take an open bet based on id'''
        with open("bet_log.json", "r") as read_file:
            bet_log = json.load(read_file)
        bet_key = 'bet_'+str(bet_id)
        try:
            # TODO: make it so you can't take your own bets

            # update bet status
            if bet_log[bet_key]['status'] in (config['bet_status']['open'],config['bet_status']['standing']):
                bet_log[bet_key]['seller'] = ctx.author.id
                bet_log[bet_key]['status'] = config['bet_status']['pending']

                # taking a standing bet creates a new bet
                if bet_log[bet_key]['status'] == config['bet_status']['standing']:
                    new_bet_id = add_new_bet(self,ctx.author.id,statement,'standing')


                with open("bet_log.json","w") as write_file:
                    json.dump(bet_log,write_file,indent=4)

                nick = await get_nick_from_id(ctx,ctx.author.id)
                await timed_send(ctx,'Bet '+str(bet_id)+' has been claimed by '+nick+'!')
            else:
                await timed_send(ctx,'That bet\'s not up for grabs!')
        except KeyError as e:
            await timed_send(ctx,'That bet doesn\'t exist!')

    @commands.command()
    async def resolve(self,ctx,bet_id):
        '''<bet_id>: resolve a pending bet or delete an open bet by id'''
        # TODO: add information to trigger the econ-bot depending on who won
        with open("bet_log.json", "r") as read_file:
            bet_log = json.load(read_file)
        bet_key = 'bet_'+str(bet_id)
        try:
            # only participants can resolve their own bets
            if self.check_author(ctx,bet_id):

                #open bids can be annulled
                if bet_log[bet_key]['status'] in (config['bet_status']['open'],config['bet_status']['standing']):
                    removed = bet_log.pop(bet_key)
                    with open("bet_log.json","w") as write_file:
                        json.dump(bet_log,write_file,indent=4)
                    nick = await get_nick_from_id(ctx,ctx.author.id)
                    await timed_send(ctx,'removed bet '+str(bet_id)+' by '+nick)

                #pending bids get set to resolved
                elif bet_log[bet_key]['status'] == config['bet_status']['pending']:
                    bet_log[bet_key]['status'] = config['bet_status']['resolved']

                    with open("bet_log.json","w") as write_file:
                        json.dump(bet_log,write_file,indent=4)

                    await timed_send(ctx,'Bet '+str(bet_id)+' has been resolved. Use !give-money <@winner> <value> to settle up.')
            else:
                await timed_send(ctx,'You can\'t resolve bets you aren\'t a part of!')
        except KeyError as e:
            raise
            #await timed_send(ctx,'That bet doesn\'t exist!')

    @commands.command()
    @commands.has_role('student')
    async def killbet(self,ctx,bet_id):
        '''Admin-only, deletes bets'''
        await timed_send(ctx,'jk this one doesn\'t work')

class Calendar(commands.Cog):

    class SchedulingProgress(Enum):
        inactive = 0
        title = 1
        date = 2
        start_time = 3
        end_time = 4
        description = 5

    def __init__(self, bot):
        self.bot = bot
        self.creds = None
        self.service = None

        self.scheduling_progress = Calendar.SchedulingProgress.inactive
        self.scheduler = None
        self.scheduled = {}

    async def cog_check(self, ctx):
        return await check_guild_role(ctx, config['staff_role'], warn=True)

    async def cog_before_invoke(self, ctx):
        if file_exists(config['google_api_auth']['token_file']):
            with open(config['google_api_auth']['token_file'], 'rb') as token:
                self.creds = await asyncify(lambda: pickle.load(token))
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                await asyncify(lambda: self.creds.refresh(Request()))
            else:
                flow = InstalledAppFlow.from_client_config(config['google_api_auth']['credentials'],
                                                           config['google_api_auth']['scopes'])
                self.creds = await asyncify(lambda: flow.run_local_server(port=0))
            with open(config['google_api_auth']['token_file'], 'wb') as token:
                await asyncify(lambda: pickle.dump(self.creds, token))
        self.service = await asyncify(lambda: build('calendar', 'v3', credentials=self.creds, cache_discovery=False))

    @commands.command()
    async def upcoming(self, ctx):
        now = datetime.datetime.utcnow()
        two_days = now + datetime.timedelta(days=2)
        events_result = await asyncify(lambda: self.service.events().list(
            calendarId=config['google_api_auth']['calendar_id'],
            timeMin=time_format(now), timeMax=time_format(two_days),
            singleEvents=True, orderBy='startTime').execute())
        events = events_result.get('items', [])
        if len(events) == 0:
            await timed_send(ctx, 'not much is happening')
        else:
            await timed_send(ctx, 'starting soon (24-hour times, Pacific):')
            now = datetime.datetime.now(datetime.timezone.utc)
            for event in events:
                if 'date' not in event['start']:
                    start = parse_datetime(event['start']['dateTime'])
                    end = parse_datetime(event['end']['dateTime'])
                    if start.date() == end.date():
                        await ctx.send('{} from {} to {}: {}'.format(
                            naturalday(start.date()),
                            start.time().strftime('%H:%M'),
                            end.time().strftime('%H:%M'),
                            event['summary']))

    @commands.Cog.listener()
    async def on_message(self, msg):
        if self.scheduling_progress != Calendar.SchedulingProgress.inactive:
            if msg.author == self.scheduler:
                if msg.content.lower().strip() in ['cancel', 'quit', 'exit']:
                    self.scheduling_progress = Calendar.SchedulingProgress.inactive
                    self.scheduler = None
                    self.scheduled = {}
                    await msg.channel.send('scheduling cancelled')
                elif self.scheduling_progress == Calendar.SchedulingProgress.title:
                    self.scheduled['title'] = msg.content.strip()
                    self.scheduling_progress = Calendar.SchedulingProgress.date
                    await msg.channel.send('give me a date (any reasonable format)')
                elif self.scheduling_progress == Calendar.SchedulingProgress.date:
                    self.scheduled['date'] = parse_datetime(msg.content.strip()).date()
                    self.scheduling_progress = Calendar.SchedulingProgress.start_time
                    await msg.channel.send('give me a start time (any reasonable format)')
                elif self.scheduling_progress == Calendar.SchedulingProgress.start_time:
                    self.scheduled['start time'] = parse_datetime(msg.content.strip()).time()
                    self.scheduling_progress = Calendar.SchedulingProgress.end_time
                    await msg.channel.send('give me a end time (any reasonable format)')
                elif self.scheduling_progress == Calendar.SchedulingProgress.end_time:
                    self.scheduled['end time'] = parse_datetime(msg.content.strip()).time()
                    self.scheduling_progress = Calendar.SchedulingProgress.description
                    await msg.channel.send('give me a description')
                elif self.scheduling_progress == Calendar.SchedulingProgress.description:
                    self.scheduled['description'] = msg.content.strip()
                    self.scheduling_progress = Calendar.SchedulingProgress.inactive
                    self.scheduler = None
                    request_body = {
                        "summary": self.scheduled['title'],
                        "description": self.scheduled['description'],
                        "start": {
                            "dateTime": datetime.datetime.combine(self.scheduled['date'], self.scheduled['start time']).isoformat(),
                            "timeZone": 'America/Los_Angeles'
                        },
                        "end": {
                            "dateTime": datetime.datetime.combine(self.scheduled['date'], self.scheduled['end time']).isoformat(),
                            "timeZone": 'America/Los_Angeles'
                        }
                    }
                    events_result = await asyncify(lambda: self.service.events().insert(
                        calendarId=config['google_api_auth']['calendar_id'],
                        body=request_body).execute())
                    await msg.channel.send('added to calendar! {}'.format(events_result['htmlLink']))

    @commands.command()
    async def schedule(self, ctx):
        self.scheduling_progress = Calendar.SchedulingProgress.title
        self.scheduler = ctx.author
        await timed_send(ctx, 'give me a title (including instructor names)')



class Admin(commands.Cog):

    async def cog_check(self, ctx):
        return await check_guild_role(ctx, config['admin_role'], warn=True)

    @commands.command()
    async def cogmod(self, ctx, cmd: str, cog: str):
        if cmd not in ['add', 'rmv']:
            await timed_send(ctx, 'First argument must be "add" or "rmv".')
            return
        if cog not in cogs:
            await timed_send(ctx, '{} is not a valid cog name.'.format(cog))
            return

        if cmd == 'add':
            bot.add_cog(cogs[cog](bot))
        elif cmd == 'rmv':
            bot.remove_cog(cog)

    @commands.command(name='reload-config')
    async def reload_config(self, ctx):
        global config
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except (JSONDecodeError, OSError) as e:
            await timed_send(ctx, 'Error reloading config. Old config unchanged.')
            await ctx.send(str(e))

cogs = {
    'welcome': Welcome,
    'calendar': Calendar,
    'bets': Bets,
    #'Admin': Admin     <-- no because this shouldn't be disabled
}

@bot.check
async def allowed_channel(ctx):
    #if ctx.channel.name != config['bot_channel']:
    #    await timed_send(ctx, 'excuse me?? I only respond in #{} okay'.format(config['bot_channel']))
    #    return False
    return True

bot.add_cog(cogs['welcome'](bot))
bot.add_cog(cogs['bets'](bot))
bot.add_cog(Admin(bot))
bot.run(config['discord_auth_token'])
