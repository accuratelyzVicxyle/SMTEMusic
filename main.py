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

# Try to use yt-dlp with updated settings
USE_YTDLP = True

# Enhanced FFmpeg options for stable streaming
ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        '-fflags +genpts -flags low_delay -strict experimental '
        '-avoid_negative_ts make_zero -fflags +nobuffer '
        '-analyzeduration 0 -probesize 32K -bufsize 512k '
        '-use_wallclock_as_timestamps 1'
    ),
    'options': '-vn -c:a libopus -b:a 128k -f opus'
}

# Updated yt-dlp configuration to handle current YouTube issues
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
    'extract_flat': False,
    'socket_timeout': 60,
    'retries': 10,
    'fragment_retries': 10,
    # Updated user agents and headers
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'http_headers': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    },
    # Try different extractor approaches
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
            'player_skip': ['configs', 'webpage', 'js'],
        }
    },
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

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

# Updated Invidious API with working instances
async def get_youtube_audio_url(query):
    """Use Invidious API to get YouTube audio with multiple fallback instances"""
    # Updated list of working Invidious instances (as of October 2024)
    invidious_instances = [
        "https://invidious.private.coffee",
        "https://invidious.perennialte.ch",
        "https://yt.artemislena.eu",
        "https://invidious.slipfox.xyz",
        "https://invidious.weblibre.org",
        "https://invidious.privacydev.net",
        "https://invidious.namazso.eu",
        "https://invidious.drgns.space",
        "https://iv.melmac.space",
        "https://invidious.protokolla.fi"
    ]
    
    # Shuffle instances to distribute load
    random.shuffle(invidious_instances)
    
    for instance in invidious_instances:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                print(f"🔍 Trying Invidious instance: {instance}")
                
                # Search for video
                encoded_query = aiohttp.helpers.quote(query, safe='')
                search_url = f"{instance}/api/v1/search?q={encoded_query}&type=video"
                
                async with session.get(search_url) as resp:
                    if resp.status == 200:
                        search_data = await resp.json()
                        if search_data and len(search_data) > 0:
                            # Get first result
                            video = search_data[0]
                            video_id = video['videoId']
                            video_title = video.get('title', 'Unknown Title')
                            
                            print(f"✅ Found video: {video_title} on {instance}")
                            
                            # Get video info with timeout
                            video_url = f"{instance}/api/v1/videos/{video_id}"
                            async with session.get(video_url) as video_resp:
                                if video_resp.status == 200:
                                    video_data = await video_resp.json()
                                    
                                    # Find best audio stream
                                    best_audio = None
                                    for format in video_data.get('adaptiveFormats', []):
                                        if 'audio' in format.get('type', '') and format.get('url'):
                                            # Prefer higher bitrate
                                            current_bitrate = format.get('bitrate', 0)
                                            if not best_audio or current_bitrate > best_audio.get('bitrate', 0):
                                                best_audio = format
                                    
                                    if best_audio:
                                        print(f"🎵 Found audio stream with bitrate: {best_audio.get('bitrate', 0)}")
                                        return {
                                            'url': best_audio['url'],
                                            'title': video_data.get('title', video_title),
                                            'duration': video_data.get('duration', 0),
                                            'webpage_url': f"https://youtube.com/watch?v={video_id}",
                                            'instance': instance
                                        }
                                    else:
                                        print(f"❌ No audio stream found for video {video_id}")
                        else:
                            print(f"❌ No search results from {instance}")
                    else:
                        print(f"❌ Search failed with status {resp.status} from {instance}")
        except asyncio.TimeoutError:
            print(f"⏰ Timeout on Invidious instance: {instance}")
            continue
        except Exception as e:
            print(f"❌ Error on Invidious instance {instance}: {str(e)}")
            continue
    
    print("❌ All Invidious instances failed")
    return None

# Alternative method using yt-dlp with updated settings
async def get_audio_with_ytdlp(query):
    """Try to get audio using yt-dlp with updated settings"""
    try:
        print(f"🔍 Trying yt-dlp for: {query}")
        
        # Try multiple approaches
        approaches = [
            query,  # Original query
            f"ytsearch:{query}",  # YouTube search
        ]
        
        for approach in approaches:
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(approach, download=False))
                
                if 'entries' in data:
                    data = data['entries'][0]
                
                if data and data.get('url'):
                    print(f"✅ yt-dlp success with approach: {approach}")
                    return {
                        'url': data['url'],
                        'title': data.get('title', 'Unknown Title'),
                        'duration': data.get('duration', 0),
                        'webpage_url': data.get('webpage_url', ''),
                        'method': 'yt-dlp'
                    }
            except Exception as e:
                print(f"❌ yt-dlp approach failed ({approach}): {str(e)}")
                continue
        
        return None
    except Exception as e:
        print(f"❌ yt-dlp completely failed: {str(e)}")
        return None

# Audio source class for yt-dlp
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')

    @classmethod
    async def from_query(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        # Try yt-dlp first
        data = await get_audio_with_ytdlp(query)
        
        # If yt-dlp fails, try Invidious
        if not data:
            print("🔄 Falling back to Invidious...")
            data = await get_youtube_audio_url(query)
        
        if not data:
            raise Exception("ไม่สามารถดึงข้อมูลเพลงได้จากแหล่งข้อมูลใดๆ")
        
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
    print(f'✅ Using updated yt-dlp configuration')
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
            player = await YTDLSource.from_query(query, loop=bot.loop)
            
            if player:
                if not ctx.voice_client.is_playing():
                    # Add small delay to ensure voice client is ready
                    await asyncio.sleep(0.3)
                    
                    def play_callback(error):
                        if error:
                            print(f"Playback error: {error}")
                        check_queue(ctx, ctx.guild.id)
                    
                    ctx.voice_client.play(player, after=play_callback)
                    
                    embed = create_embed("🎵 กำลังเล่นเพลง", 
                                        f"**{player.title}**\n\nขอให้คุณสนุกกับการฟังเพลง! 🎶")
                    await ctx.send(embed=embed)
                else:
                    guild_id = ctx.guild.id
                    if guild_id not in queues:
                        queues[guild_id] = []
                    queues[guild_id].append(player)
                    
                    embed = create_embed("✅ เพิ่มเพลงในคิวแล้ว", 
                                        f"**{player.title}**\n\nตำแหน่งในคิว: #{len(queues[guild_id])}")
                    await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Final error: {error_msg}")
            
            embed = create_embed("❌ เกิดข้อผิดพลาด", 
                f"ไม่สามารถเล่นเพลงได้\n\n"
                f"**รายละเอียด:** {error_msg}\n\n"
                f"**โปรดลอง:**\n"
                f"• ใช้คำค้นหาที่แตกต่าง\n"
                f"• ลองลิงก์ YouTube โดยตรง\n"
                f"• รอสักครู่แล้วลองใหม่\n"
                f"• ติดต่อผู้พัฒนาหากปัญหายังคงมี", 0xff0000)
            await ctx.send(embed=embed)

@bot.command()
async def status(ctx):
    """แสดงสถานะบอท"""
    embed = create_embed("📊 สถานะบอท", 
        f"**แหล่งข้อมูลหลัก:** yt-dlp + Invidious Fallback\n"
        f"**เซิร์ฟเวอร์:** {len(bot.guilds)}\n"
        f"**พิง:** {round(bot.latency * 1000)}ms\n"
        f"**คิวเพลง:** {sum(len(q) for q in queues.values())} เพลง", 0x0099ff)
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
        print(f"✅ ใช้ yt-dlp เป็นแหล่งข้อมูลหลัก")
        print(f"✅ มี Invidious เป็น fallback")
        bot.run(token)
