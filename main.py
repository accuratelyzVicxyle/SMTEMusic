import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import aiohttp
import json
import random
import time

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Large Image URL
LARGE_IMAGE_URL = "https://media.discordapp.net/attachments/856506862107492402/1425324515034009662/image.png?ex=68e72c65&is=68e5dae5&hm=390850b95ebb0c2bc1eacddd8bdaba22eef053c967a638122fe570bdfb18b724&=&format=webp&quality=lossless"

# Music queues
queues = {}

# Track usage to detect when to switch methods
usage_count = 0
last_method_switch = time.time()
current_primary_method = "invidious"  # Start with invidious

# FFmpeg options
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# Multiple yt-dlp configurations for rotation
ytdl_configs = [
    {  # Config 1 - Standard
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
        'extract_flat': False,
        'socket_timeout': 60,
        'retries': 10,
        'fragment_retries': 10,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    },
    {  # Config 2 - Alternative
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
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
        'extract_flat': False,
        'socket_timeout': 60,
        'retries': 8,
        'fragment_retries': 8,
        'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    },
    {  # Config 3 - Mobile user agent
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
        'extract_flat': False,
        'socket_timeout': 60,
        'retries': 12,
        'fragment_retries': 12,
        'user_agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    }
]

# Current yt-dlp config index
current_ytdl_config = 0

def get_current_ytdl():
    """Get current yt-dlp configuration"""
    return yt_dlp.YoutubeDL(ytdl_configs[current_ytdl_config])

# Embed creation function with LARGE IMAGE
def create_embed(title, description, color=0x00ff00, show_large_image=True):
    """Create embed message with LARGE image (not thumbnail)"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    
    # Use LARGE image instead of small thumbnail
    if show_large_image:
        embed.set_image(url=LARGE_IMAGE_URL)
    
    embed.set_footer(text="Music Bot • Made with ❤️")
    return embed

# Enhanced Invidious API with multiple instances and retries
async def get_youtube_audio_url(query):
    """Use Invidious API to avoid yt-dlp issues with multiple instances"""
    invidious_instances = [
        "https://vid.puffyan.us",
        "https://inv.riverside.rocks", 
        "https://yt.artemislena.eu",
        "https://invidious.snopyta.org",
        "https://yewtu.be",
        "https://invidious.weblibre.org",
        "https://invidious.esmailelbob.xyz",
        "https://inv.bp.projectsegfau.lt"
    ]
    
    # Shuffle instances to distribute load
    random.shuffle(invidious_instances)
    
    for instance in invidious_instances:
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Search for video
                async with session.get(f"{instance}/api/v1/search?q={query}&type=video") as resp:
                    if resp.status == 200:
                        search_data = await resp.json()
                        if search_data and len(search_data) > 0:
                            # Get first result
                            video_id = search_data[0]['videoId']
                            
                            # Get video info with timeout
                            async with session.get(f"{instance}/api/v1/videos/{video_id}") as video_resp:
                                if video_resp.status == 200:
                                    video_data = await video_resp.json()
                                    
                                    # Find best audio stream
                                    best_audio = None
                                    for format in video_data.get('adaptiveFormats', []):
                                        if 'audio' in format.get('type', '') and format.get('url'):
                                            if not best_audio or format.get('bitrate', 0) > best_audio.get('bitrate', 0):
                                                best_audio = format
                                    
                                    if best_audio:
                                        return {
                                            'url': best_audio['url'],
                                            'title': video_data['title'],
                                            'duration': video_data.get('duration', 0),
                                            'webpage_url': f"https://youtube.com/watch?v={video_id}",
                                            'instance': instance
                                        }
        except Exception as e:
            print(f"Invidious instance {instance} failed: {e}")
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
        ytdl = get_current_ytdl()
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

def rotate_method():
    """Rotate between different methods to avoid detection"""
    global current_primary_method, current_ytdl_config, usage_count, last_method_switch
    
    usage_count += 1
    current_time = time.time()
    
    # Rotate method every 50 requests or 2 hours, whichever comes first
    if usage_count >= 50 or (current_time - last_method_switch) >= 7200:
        if current_primary_method == "invidious":
            current_primary_method = "ytdl"
            # Also rotate yt-dlp config
            current_ytdl_config = (current_ytdl_config + 1) % len(ytdl_configs)
        else:
            current_primary_method = "invidious"
        
        usage_count = 0
        last_method_switch = current_time
        print(f"🔄 Switched primary method to: {current_primary_method}")

# Bot events
@bot.event
async def on_ready():
    print(f'✅ {bot.user} has logged in!')
    print(f'✅ Bot is in {len(bot.guilds)} servers')
    print(f'✅ Primary method: {current_primary_method}')
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
        embed = create_embed("❌ ข้อผิดพลาด", "คุณต้องอยู่ในช่องเสียงก่อน!", 0xff0000)
        await ctx.send(embed=embed)
        return
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    
    embed = create_embed("🎵 เข้าร่วมช่องเสียงแล้ว", f"เข้าร่วมช่องเสียง **{channel.name}** แล้ว พร้อมเปิดเพลง!")
    await ctx.send(embed=embed)

@bot.command()
async def play(ctx, *, query):
    """เล่นเพลงจาก YouTube"""
    if not ctx.author.voice:
        embed = create_embed("❌ ข้อผิดพลาด", "คุณต้องอยู่ในช่องเสียงก่อน!", 0xff0000)
        await ctx.send(embed=embed)
        return
    
    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()
    
    async with ctx.typing():
        try:
            player = None
            method_used = "ไม่ทราบ"
            
            # Rotate method to avoid detection
            rotate_method()
            
            # Try methods based on current primary method
            if current_primary_method == "invidious":
                # Try Invidious first, then yt-dlp
                try:
                    player = await InvidiousSource.from_query(query, loop=bot.loop)
                    method_used = "Invidious"
                except Exception as e1:
                    print(f"Invidious failed: {e1}")
                    try:
                        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
                        method_used = f"YouTube Direct (Config {current_ytdl_config + 1})"
                    except Exception as e2:
                        print(f"yt-dlp failed: {e2}")
                        raise Exception(f"ไม่สามารถดึงข้อมูลเพลงได้: {str(e2)}")
            else:
                # Try yt-dlp first, then Invidious
                try:
                    player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
                    method_used = f"YouTube Direct (Config {current_ytdl_config + 1})"
                except Exception as e1:
                    print(f"yt-dlp failed: {e1}")
                    try:
                        player = await InvidiousSource.from_query(query, loop=bot.loop)
                        method_used = "Invidious"
                    except Exception as e2:
                        print(f"Invidious failed: {e2}")
                        raise Exception(f"ไม่สามารถดึงข้อมูลเพลงได้: {str(e2)}")
            
            if player:
                if not ctx.voice_client.is_playing():
                    ctx.voice_client.play(player, after=lambda x=None: check_queue(ctx, ctx.guild.id))
                    embed = create_embed("🎵 กำลังเล่นเพลง", f"**{player.title}**\n\nผ่าน: {method_used}\n\nขอให้คุณสนุกกับการฟังเพลง! 🎶")
                    await ctx.send(embed=embed)
                else:
                    guild_id = ctx.guild.id
                    if guild_id not in queues:
                        queues[guild_id] = []
                    queues[guild_id].append(player)
                    embed = create_embed("✅ เพิ่มเพลงในคิวแล้ว", f"**{player.title}**\n\nตำแหน่งในคิว: #{len(queues[guild_id])}")
                    await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = str(e)
            # Rotate method on error
            global current_primary_method
            current_primary_method = "invidious" if current_primary_method == "ytdl" else "ytdl"
            print(f"🔄 Method rotated due to error. New method: {current_primary_method}")
            
            embed = create_embed("❌ เกิดข้อผิดพลาด", 
                f"ไม่สามารถเล่นเพลงได้\n\n"
                f"**ข้อความ:** {error_msg}\n\n"
                f"กำลังลองวิธีอื่น...\n"
                f"กรุณาลองคำสั่งอีกครั้ง", 0xff0000)
            await ctx.send(embed=embed)

@bot.command()
async def status(ctx):
    """แสดงสถานะบอท"""
    embed = create_embed("📊 สถานะบอท", 
        f"**วิธีการหลัก:** {current_primary_method}\n"
        f"**จำนวนการใช้งาน:** {usage_count}\n"
        f"**คอนฟิก yt-dlp:** {current_ytdl_config + 1}\n"
        f"**เซิร์ฟเวอร์:** {len(bot.guilds)}\n"
        f"**พิง:** {round(bot.latency * 1000)}ms", 0x0099ff)
    await ctx.send(embed=embed)

@bot.command()
async def pause(ctx):
    """หยุดเพลงชั่วคราว"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        embed = create_embed("⏸️ หยุดชั่วคราว", "เพลงถูกหยุดชั่วคราวแล้ว ใช้ `!resume` เพื่อเล่นต่อ", 0xffa500)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("❌ ข้อผิดพลาด", "ไม่มีเพลงที่กำลังเล่นอยู่", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def resume(ctx):
    """เล่นเพลงต่อ"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        embed = create_embed("▶️ เล่นต่อ", "เพลงกำลังเล่นต่อแล้ว! 🎶", 0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("❌ ข้อผิดพลาด", "ไม่มีเพลงที่ถูกหยุดชั่วคราว", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def stop(ctx):
    """หยุดเพลงและล้างคิว"""
    if ctx.voice_client:
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
    
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id] = []
    
    embed = create_embed("⏹️ หยุดเพลง", "เพลงถูกหยุดและคิวถูกล้างเรียบร้อยแล้ว", 0xff0000)
    await ctx.send(embed=embed)

@bot.command()
async def skip(ctx):
    """ข้ามเพลงปัจจุบัน"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        embed = create_embed("⏭️ ข้ามเพลง", "ข้ามเพลงปัจจุบันเรียบร้อยแล้ว!", 0x00ff00)
        await ctx.send(embed=embed)
        check_queue(ctx, ctx.guild.id)
    else:
        embed = create_embed("❌ ข้อผิดพลาด", "ไม่มีเพลงที่กำลังเล่นอยู่", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def queue(ctx):
    """แสดงคิวเพลง"""
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        queue_list = "\n".join([f"**{i+1}.** {song.title}" for i, song in enumerate(queues[guild_id])])
        if len(queue_list) > 2000:
            queue_list = queue_list[:1997] + "..."
        
        embed = create_embed("📋 คิวเพลง", f"มี {len(queues[guild_id])} เพลงในคิว:\n\n{queue_list}", 0x0099ff)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("📋 คิวเพลง", "❌ ไม่มีเพลงในคิว", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def leave(ctx):
    """ออกจากช่องเสียง"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        embed = create_embed("👋 ออกจากช่องเสียง", "บอทได้ออกจากช่องเสียงแล้ว ขอบคุณที่ใช้บริการ! 🎵", 0x00ff00)
        await ctx.send(embed=embed)
        
        guild_id = ctx.guild.id
        if guild_id in queues:
            del queues[guild_id]
    else:
        embed = create_embed("❌ ข้อผิดพลาด", "บอทไม่ได้อยู่ในช่องเสียง", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    """ทดสอบการตอบสนอง"""
    latency = round(bot.latency * 1000)
    embed = create_embed("🏓 Pong!", f"ความเร็วในการตอบสนอง: **{latency}ms**\n\nบอททำงานปกติ! ✅", 0x00ff00)
    await ctx.send(embed=embed)

@bot.command()
async def volume(ctx, volume: int):
    """ปรับระดับเสียง (0-100)"""
    if ctx.voice_client is None:
        embed = create_embed("❌ ข้อผิดพลาด", "ไม่ได้เชื่อมต่อกับช่องเสียง", 0xff0000)
        return await ctx.send(embed=embed)
    
    if 0 <= volume <= 100:
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = volume / 100
        embed = create_embed("🔊 ระดับเสียง", f"ตั้งค่าระดับเสียงเป็น **{volume}%** แล้ว", 0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("❌ ข้อผิดพลาด", "กรุณาใส่ตัวเลขระหว่าง 0-100", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def nowplaying(ctx):
    """แสดงเพลงที่กำลังเล่นอยู่"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        embed = create_embed("🎵 กำลังเล่นอยู่", "กำลังเล่นเพลง...\n\nใช้ `!queue` เพื่อดูคิวเพลง", 0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("🎵 กำลังเล่นอยู่", "❌ ไม่มีเพลงที่กำลังเล่นอยู่", 0xff0000)
        await ctx.send(embed=embed)

@bot.command()
async def help_bot(ctx):
    """แสดงคำสั่งทั้งหมด"""
    commands_list = """
**🎵 คำสั่งเพลง:**
`!play [ชื่อเพลง/ลิงก์]` - เล่นเพลงจาก YouTube
`!pause` - หยุดเพลงชั่วคราว
`!resume` - เล่นเพลงต่อ
`!stop` - หยุดและล้างคิว
`!skip` - ข้ามเพลงปัจจุบัน
`!queue` - แสดงคิวเพลง
`!volume [0-100]` - ปรับระดับเสียง
`!nowplaying` - แสดงเพลงที่กำลังเล่น
`!status` - แสดงสถานะบอท

**🔊 คำสั่งเสียง:**
`!join` - เข้าร่วมช่องเสียง
`!leave` - ออกจากช่องเสียง

**ℹ️ คำสั่งข้อมูล:**
`!ping` - ทดสอบการตอบสนอง
`!help_bot` - แสดงคำสั่งทั้งหมด
"""
    embed = create_embed("🤖 คำสั่งบอท", commands_list, 0x0099ff)
    await ctx.send(embed=embed)

# Run bot
if __name__ == "__main__":
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print("❌ ตั้งค่า DISCORD_TOKEN ใน Environment Variables")
        print("💡 ไปที่ Railway Dashboard → Variables → Add DISCORD_TOKEN")
    else:
        print("🎵 เริ่มต้นบอทเพลง Discord บน Railway...")
        print(f"✅ วิธีการเริ่มต้น: {current_primary_method}")
        bot.run(token)
