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

# Latest yt-dlp configuration for October 2024
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
    
    # Critical fixes for YouTube
    'extract_flat': False,
    'socket_timeout': 30,
    'retries': 15,
    'fragment_retries': 15,
    'skip_unavailable_fragments': True,
    'keep_fragments': True,
    
    # Updated user agent and headers
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    
    'http_headers': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    },
    
    # YouTube specific fixes
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web', 'ios'],
            'player_skip': ['configs', 'webpage', 'js'],
        }
    },
    
    # Force specific formats to avoid issues
    'format_sort': ['res:720', 'ext:mp4:m4a', 'acodec:mp3'],
    'prefer_free_formats': True,
    
    # Additional YouTube parameters
    'youtube_include_dash_manifest': False,
    'youtube_include_hls_manifest': False,
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

# Simple YouTube audio extraction using yt-dlp only
async def get_youtube_audio_simple(query):
    """Simple method using only yt-dlp with latest fixes"""
    try:
        print(f"🎵 Attempting to play: {query}")
        
        # Try direct extraction first
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
            
            if 'entries' in data:
                data = data['entries'][0]
            
            if data and data.get('url'):
                print(f"✅ Successfully extracted audio URL")
                return {
                    'url': data['url'],
                    'title': data.get('title', 'Unknown Title'),
                    'duration': data.get('duration', 0),
                    'webpage_url': data.get('webpage_url', ''),
                    'method': 'yt-dlp'
                }
        except Exception as e:
            print(f"❌ Direct extraction failed: {str(e)}")
            
            # Try with ytsearch fallback
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))
                
                if 'entries' in data and data['entries']:
                    data = data['entries'][0]
                    
                    if data and data.get('url'):
                        print(f"✅ Success with ytsearch fallback")
                        return {
                            'url': data['url'],
                            'title': data.get('title', 'Unknown Title'),
                            'duration': data.get('duration', 0),
                            'webpage_url': data.get('webpage_url', ''),
                            'method': 'yt-dlp (search)'
                        }
            except Exception as e2:
                print(f"❌ ytsearch also failed: {str(e2)}")
                raise Exception(f"All extraction methods failed")
        
        return None
        
    except Exception as e:
        print(f"❌ Complete failure: {str(e)}")
        raise e

# Audio source class
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')

    @classmethod
    async def from_query(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        data = await get_youtube_audio_simple(query)
        
        if not data:
            raise Exception("Failed to extract audio data")
        
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
    print(f'✅ Using latest yt-dlp configuration')
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
            
            # More helpful error message
            if "Sign in to confirm" in error_msg:
                error_display = "YouTube ตรวจพบการใช้งานจากเซิร์ฟเวอร์\nกรุณาลองเพลงอื่นหรือรอสักครู่"
            elif "Failed to extract" in error_msg:
                error_display = "YouTube ปรับเปลี่ยนระบบชั่วคราว\nกรุณาลองเพลงอื่นหรือใช้ลิงก์ YouTube โดยตรง"
            else:
                error_display = error_msg
            
            embed = create_embed("❌ เกิดข้อผิดพลาด", 
                f"ไม่สามารถเล่นเพลงได้\n\n"
                f"**สาเหตุ:** {error_display}\n\n"
                f"**วิธีแก้ไข:**\n"
                f"• ลองเพลงอื่น\n"
                f"• ใช้ลิงก์ YouTube โดยตรง\n"
                f"• รอ 5-10 นาทีแล้วลองใหม่\n"
                f"• ลองค้นหาด้วยชื่อเพลงแทนลิงก์", 0xff0000)
            await ctx.send(embed=embed)

@bot.command()
async def status(ctx):
    """แสดงสถานะบอท"""
    embed = create_embed("📊 สถานะบอท", 
        f"**สถานะ:** {'✅ ทำงานปกติ' if bot.is_ready() else '❌ มีปัญหา'}\n"
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
        print("✅ ใช้ yt-dlp การตั้งค่าล่าสุด")
        bot.run(token)
