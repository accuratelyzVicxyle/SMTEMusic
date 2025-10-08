import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import aiohttp
import json

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Thumbnail URL
THUMBNAIL_URL = "https://media.discordapp.net/attachments/856506862107492402/1425324515034009662/image.png?ex=68e72c65&is=68e5dae5&hm=390850b95ebb0c2bc1eacddd8bdaba22eef053c967a638122fe570bdfb18b724&=&format=webp&quality=lossless"

# Music queues
queues = {}

# FFmpeg options
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# yt-dlp configuration
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    
    # Anti-blocking options
    'extract_flat': False,
    'socket_timeout': 60,
    'retries': 15,
    'fragment_retries': 15,
    'skip_unavailable_fragments': True,
    'keep_fragments': True,
    
    # User Agent
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    
    # HTTP headers
    'http_headers': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    },
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Embed creation function
def create_embed(title, description, color=0x00ff00):
    """Create embed message with thumbnail"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text="Music Bot • Made with ❤️")
    return embed

# Invidious API for YouTube audio
async def get_youtube_audio_url(query):
    """Use Invidious API to avoid yt-dlp issues"""
    invidious_instances = [
        "https://vid.puffyan.us",
        "https://inv.riverside.rocks", 
        "https://yt.artemislena.eu",
        "https://invidious.snopyta.org",
        "https://yewtu.be"
    ]
    
    for instance in invidious_instances:
        try:
            async with aiohttp.ClientSession() as session:
                # Search for video
                async with session.get(f"{instance}/api/v1/search?q={query}") as resp:
                    if resp.status == 200:
                        search_data = await resp.json()
                        if search_data and len(search_data) > 0:
                            video_id = search_data[0]['videoId']
                            
                            # Get video info
                            async with session.get(f"{instance}/api/v1/videos/{video_id}") as video_resp:
                                if video_resp.status == 200:
                                    video_data = await video_resp.json()
                                    
                                    # Find audio stream
                                    for format in video_data.get('adaptiveFormats', []):
                                        if 'audio' in format.get('type', '') and format.get('url'):
                                            return {
                                                'url': format['url'],
                                                'title': video_data['title'],
                                                'duration': video_data.get('duration', 0),
                                                'webpage_url': f"https://youtube.com/watch?v={video_id}"
                                            }
        except Exception:
            continue
    
    return None

# Audio source classes
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]
        
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class InvidiousSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')

    @classmethod
    async def from_query(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await get_youtube_audio_url(query)
        
        if not data:
            raise Exception("Cannot fetch music data from Invidious")
        
        filename = data['url']
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Queue management
def check_queue(ctx, guild_id):
    if queues.get(guild_id):
        if len(queues[guild_id]) > 0:
            source = queues[guild_id].pop(0)
            ctx.voice_client.play(source, after=lambda x=None: check_queue(ctx, guild_id))

# Bot events
@bot.event
async def on_ready():
    print(f'✅ {bot.user} has logged in!')
    print(f'✅ Bot is in {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!play"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Error: {error}")

# Bot commands
@bot.command()
async def join(ctx):
    """Join voice channel"""
    if not ctx.author.voice:
        embed = create_embed("❌ Error", "You need to be in a voice channel first!", 0xff0000)
        await ctx.send(embed=embed)
        return
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    
    embed = create_embed("🎵 Joined Voice Channel", f"Joined **{channel.name}** and ready to play music!")
    await ctx.send(embed=embed)

@bot.command()
async def play(ctx, *, query):
    """Play music from YouTube"""
    if not ctx.author.voice:
        embed = create_embed("❌ Error", "You need to be in a voice channel first!", 0xff0000)
        await ctx.send(embed=embed)
        return
    
    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()
    
    async with ctx.typing():
        try:
            player = None
            method_used = "Unknown"
            
            # Try Invidious first (more reliable)
            try:
                player = await InvidiousSource.from_query(query, loop=bot.loop)
                method_used = "Invidious"
            except Exception as e1:
                print(f"Invidious failed: {e1}")
                
                # Fallback to yt-dlp
                try:
                    player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
                    method_used = "YouTube Direct"
                except Exception as e2:
                    print(f"yt-dlp failed: {e2}")
                    raise Exception(f"Cannot fetch music: {str(e2)}")
            
            if player:
                if not ctx.voice_client.is_playing():
                    ctx.voice_client.play(player, after=lambda x=None: check_queue(ctx, ctx.guild.id))
                    embed = create_embed("🎵 Now Playing", f"**{player.title}**\n\nVia: {method_used}\n\nEnjoy the music! 🎶")
                    await ctx.send(embed=embed)
                else:
                    guild_id = ctx.guild.id
                    if guild_id not in queues:
                        queues[guild_id] = []
                    queues[guild_id].append(player)
                    embed = create_embed("✅ Added to Queue", f"**{player.title}**\n\nQueue position: #{len(queues[guild_id])}")
                    await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = str(e)
            embed = create_embed("❌ Error", 
                f"Cannot play music\n\n"
                f"**Message:** {error_msg}\n\n"
                f"Please try:\n"
                f"• Different song\n"
                f"• New search\n"
                f"• Wait a moment", 0xff0000)
            await ctx.send(embed=embed)

@bot.command()
async def pause(ctx):
    """Pause current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        embed = create_embed("⏸️ Paused", "Music paused. Use `!resume` to continue.", 0xffa500)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("❌ Error", "No music is playing", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def resume(ctx):
    """Resume paused song"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        embed = create_embed("▶️ Resumed", "Music resumed! 🎶", 0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("❌ Error", "No music is paused", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def stop(ctx):
    """Stop music and clear queue"""
    if ctx.voice_client:
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
    
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id] = []
    
    embed = create_embed("⏹️ Stopped", "Music stopped and queue cleared", 0xff0000)
    await ctx.send(embed=embed)

@bot.command()
async def skip(ctx):
    """Skip current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        embed = create_embed("⏭️ Skipped", "Skipped current song!", 0x00ff00)
        await ctx.send(embed=embed)
        check_queue(ctx, ctx.guild.id)
    else:
        embed = create_embed("❌ Error", "No music is playing", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def queue(ctx):
    """Show music queue"""
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        queue_list = "\n".join([f"**{i+1}.** {song.title}" for i, song in enumerate(queues[guild_id])])
        if len(queue_list) > 2000:
            queue_list = queue_list[:1997] + "..."
        
        embed = create_embed("📋 Music Queue", f"{len(queues[guild_id])} songs in queue:\n\n{queue_list}", 0x0099ff)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("📋 Music Queue", "❌ No songs in queue", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def leave(ctx):
    """Leave voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        embed = create_embed("👋 Left Voice Channel", "Bot has left the voice channel. Thank you for using the service! 🎵", 0x00ff00)
        await ctx.send(embed=embed)
        
        guild_id = ctx.guild.id
        if guild_id in queues:
            del queues[guild_id]
    else:
        embed = create_embed("❌ Error", "Bot is not in a voice channel", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    """Test bot responsiveness"""
    latency = round(bot.latency * 1000)
    embed = create_embed("🏓 Pong!", f"Response time: **{latency}ms**\n\nBot is working normally! ✅", 0x00ff00)
    await ctx.send(embed=embed)

@bot.command()
async def volume(ctx, volume: int):
    """Adjust volume (0-100)"""
    if ctx.voice_client is None:
        embed = create_embed("❌ Error", "Not connected to voice channel", 0xff0000)
        return await ctx.send(embed=embed)
    
    if 0 <= volume <= 100:
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = volume / 100
        embed = create_embed("🔊 Volume", f"Volume set to **{volume}%**", 0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("❌ Error", "Please enter a number between 0-100", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def nowplaying(ctx):
    """Show currently playing song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        embed = create_embed("🎵 Now Playing", "A song is currently playing...\n\nUse `!queue` to see the queue", 0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("🎵 Now Playing", "❌ No music is playing", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def help_bot(ctx):
    """Show all available commands"""
    commands_list = """
**🎵 Music Commands:**
`!play [song/url]` - Play music from YouTube
`!pause` - Pause current song
`!resume` - Resume paused song
`!stop` - Stop music and clear queue
`!skip` - Skip current song
`!queue` - Show music queue
`!volume [0-100]` - Adjust volume
`!nowplaying` - Show current song

**🔊 Voice Commands:**
`!join` - Join voice channel
`!leave` - Leave voice channel

**ℹ️ Info Commands:**
`!ping` - Test bot responsiveness
`!help_bot` - Show this help message
"""
    embed = create_embed("🤖 Bot Help", commands_list, 0x0099ff)
    await ctx.send(embed=embed)

# Run bot
if __name__ == "__main__":
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print("❌ Please set DISCORD_TOKEN in Environment Variables")
        print("💡 Go to Railway Dashboard → Variables → Add DISCORD_TOKEN")
    else:
        print("🎵 Starting Discord Music Bot on Railway...")
        bot.run(token)
