import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import aiohttp
import json

# โค้ดบอทของคุณ
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# URL ภาพ thumbnail
THUMBNAIL_URL = "https://media.discordapp.net/attachments/856506862107492402/1425324515034009662/image.png?ex=68e72c65&is=68e5dae5&hm=390850b95ebb0c2bc1eacddd8bdaba22eef053c967a638122fe570bdfb18b724&=&format=webp&quality=lossless"

queues = {}

# ตั้งค่า FFmpeg
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

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
    
    # Options สำหรับแก้ปัญหาใหม่
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

async def get_youtube_audio_url(query):
    """ใช้ Invidious API เพื่อหลีกเลี่ยงปัญหา yt-dlp"""
    invidious_instances = [
        "https://vid.puffyan.us",
        "https://inv.riverside.rocks", 
        "https://yt.artemislena.eu",
    ]
    
    for instance in invidious_instances:
        try:
            async with aiohttp.ClientSession() as session:
                # ค้นหาวิดีโอ
                async with session.get(f"{instance}/api/v1/search?q={query}") as resp:
                    if resp.status == 200:
                        search_data = await resp.json()
                        if search_data and len(search_data) > 0:
                            video_id = search_data[0]['videoId']
                            
                            # รับข้อมูลวิดีโอ
                            async with session.get(f"{instance}/api/v1/videos/{video_id}") as video_resp:
                                if video_resp.status == 200:
                                    video_data = await video_resp.json()
                                    
                                    # หา audio stream
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
            raise Exception("ไม่สามารถดึงข้อมูลเพลงได้จาก Invidious")
        
        filename = data['url']
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
            
            # ลองใช้ Invidious ก่อน
            try:
                player = await InvidiousSource.from_query(query, loop=bot.loop)
                method_used = "Invidious"
            except Exception as e1:
                print(f"Invidious failed: {e1}")
                
                # ลองใช้ yt-dlp
                try:
                    player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
                    method_used = "YouTube Direct"
                except Exception as e2:
                    print(f"yt-dlp failed: {e2}")
                    raise Exception(f"ไม่สามารถดึงข้อมูลเพลงได้")
            
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
            embed = create_embed("❌ เกิดข้อผิดพลาด", 
                f"ไม่สามารถเล่นเพลงได้\n\n"
                f"**ข้อความ:** {error_msg}\n\n"
                f"กรุณาลอง:\n"
                f"• เพลงอื่น\n"
                f"• ค้นหาใหม่\n"
                f"• รอสักครู่", 0xff0000)
            await ctx.send(embed=embed)

# ... (คำสั่งอื่นๆ เหมือนเดิม) ...

if __name__ == "__main__":
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print("❌ ตั้งค่า DISCORD_TOKEN ใน Environment Variables")
    else:
        bot.run(token)
