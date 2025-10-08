import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio

# โค้ดบอทของคุณ (ใช้โค้ดเดิมที่ให้ไป)
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# URL ภาพ thumbnail
THUMBNAIL_URL = "https://media.discordapp.net/attachments/856506862107492402/1425324515034009662/image.png?ex=68e72c65&is=68e5dae5&hm=390850b95ebb0c2bc1eacddd8bdaba22eef053c967a638122fe570bdfb18b724&=&format=webp&quality=lossless"

queues = {}

# ตั้งค่า yt-dlp
# ตั้งค่า yt-dlp ที่อัพเดตแล้ว
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
    
    # Options สำหรับหลีกเลี่ยงการบล็อก
    'extract_flat': False,
    'socket_timeout': 60,
    'retries': 20,
    'fragment_retries': 20,
    'skip_unavailable_fragments': True,
    'keep_fragments': True,
    'continue_dl': True,
    'no_part': True,
    'noprogress': True,
    
    # User Agent ที่หลากหลายและใหม่กว่า
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    
    # HTTP headers เพิ่มเติม
    'http_headers': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    },
    
    # Extractor arguments ที่หลากหลาย
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web', 'ios', 'android_embedded', 'tv_embedded'],
            'player_skip': ['configs', 'webpage', 'js'],
            'skip': ['dash', 'hls']
        }
    },
    
    # Postprocessor args
    'postprocessor_args': {
        'ffmpeg': ['-ac', '2']
    },
    
    # Throttling เพื่อเลี่ยง rate limits
    'throttled_rate': '512K',
    'ratelimit': 1048576,
    
    # ใช้ format ที่หลากหลาย
    'format_sort': ['res:720', 'ext:mp4:m4a', 'acodec:mp3'],
    'prefer_free_formats': True,
    
    # Mark watched เพื่อหลีกเลี่ยงการติดตาม
    'mark_watched': False,
    'no_overwrites': True,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

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

def check_queue(ctx, guild_id):
    if queues.get(guild_id):
        if len(queues[guild_id]) > 0:
            source = queues[guild_id].pop(0)
            ctx.voice_client.play(source, after=lambda x=None: check_queue(ctx, guild_id))

def create_embed(title, description, color=0x00ff00):
    """สร้าง Embed message ด้วย thumbnail และ styling"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=THUMBNAIL_URL)
    embed.set_footer(text="Music Bot • Made with ❤️")
    return embed

@bot.event
async def on_ready():
    print(f'✅ {bot.user} has logged in!')
    print(f'✅ Bot is in {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!play"))

@bot.command()
async def join(ctx):
    """เข้าร่วมช่องเสียง"""
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
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            
            if not ctx.voice_client.is_playing():
                ctx.voice_client.play(player, after=lambda x=None: check_queue(ctx, ctx.guild.id))
                embed = create_embed("🎵 กำลังเล่นเพลง", f"**{player.title}**\n\nขอให้คุณสนุกกับการฟังเพลง! 🎶")
                await ctx.send(embed=embed)
            else:
                guild_id = ctx.guild.id
                if guild_id not in queues:
                    queues[guild_id] = []
                queues[guild_id].append(player)
                embed = create_embed("✅ เพิ่มเพลงในคิวแล้ว", f"**{player.title}**\n\nเพลงนี้ถูกเพิ่มในคิวเรียบร้อยแล้ว!")
                await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = str(e)
            if "Sign in to confirm you're not a bot" in error_msg:
                embed = create_embed("❌ เกิดข้อผิดพลาด", "YouTube ตรวจพบว่าเป็นการดาวน์โหลดจากเซิร์ฟเวอร์ กรุณาลองเพลงอื่นหรือลองใหม่ในภายหลัง", 0xff0000)
            else:
                embed = create_embed("❌ เกิดข้อผิดพลาด", f"```{error_msg}```", 0xff0000)
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
        # เนื่องจากเราเก็บข้อมูลเพลงใน source เราอาจต้องปรับปรุง这部分
        embed = create_embed("🎵 กำลังเล่นอยู่", "กำลังเล่นเพลง...\n\nใช้ `!queue` เพื่อดูคิวเพลง", 0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = create_embed("🎵 กำลังเล่นอยู่", "❌ ไม่มีเพลงที่กำลังเล่นอยู่", 0xff0000)
        await ctx.send(embed=embed)

if __name__ == "__main__":
    # ใช้ environment variable บน Railway
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print("❌ ตั้งค่า DISCORD_TOKEN ใน Environment Variables")
    else:
        bot.run(token)
