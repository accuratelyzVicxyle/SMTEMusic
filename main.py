import os
import discord
from discord.ext import commands
import asyncio
import aiohttp
import random
import urllib.parse

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

# Updated working Invidious instances (December 2024)
async def get_working_invidious_instances():
    """Get list of currently working Invidious instances"""
    return [
        "https://inv.riverside.rocks",
        "https://invidious.private.coffee",
        "https://yt.artemislena.eu",
        "https://invidious.slipfox.xyz",
        "https://invidious.privacydev.net",
        "https://invidious.namazso.eu",
        "https://yewtu.be",
        "https://invidious.projectsegfau.lt",
        "https://iv.melmac.space",
        "https://invidious.nerdvpn.de",
        "https://inv.bp.projectsegfau.lt",
        "https://invidious.no-logs.com",
        "https://invidious.epicsite.xyz",
        "https://invidious.protokolla.fi",
        "https://vid.puffyan.us"
    ]

# Extract video ID from YouTube URL
def extract_video_id(query):
    """Extract video ID from YouTube URL or return the query as search term"""
    query = query.strip()
    
    # If it's a YouTube URL, extract the video ID
    if 'youtube.com/watch?v=' in query:
        return query.split('v=')[1].split('&')[0]
    elif 'youtu.be/' in query:
        return query.split('youtu.be/')[1].split('?')[0]
    elif 'youtube.com/embed/' in query:
        return query.split('embed/')[1].split('?')[0]
    else:
        # It's a search query, return as is
        return None

# Test if an Invidious instance is working
async def test_invidious_instance(instance):
    """Test if an Invidious instance is working"""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Test with a simple API call
            test_url = f"{instance}/api/v1/stats"
            async with session.get(test_url) as resp:
                return resp.status == 200
    except:
        return False

# Get working instances with testing
async def get_tested_instances():
    """Get and test Invidious instances"""
    instances = await get_working_invidious_instances()
    working_instances = []
    
    # Test instances concurrently
    tasks = [test_invidious_instance(instance) for instance in instances]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, instance in enumerate(instances):
        if results[i] is True:
            working_instances.append(instance)
    
    # If no instances are working, return the original list as fallback
    return working_instances if working_instances else instances

# Search for video using Invidious
async def search_invidious_video(query):
    """Search for a video using Invidious API"""
    instances = await get_tested_instances()
    if not instances:
        instances = await get_working_invidious_instances()
    
    random.shuffle(instances)  # Shuffle for load balancing
    
    video_id = extract_video_id(query)
    
    for instance in instances:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if video_id:
                    # Direct video access
                    video_url = f"{instance}/api/v1/videos/{video_id}"
                    async with session.get(video_url) as resp:
                        if resp.status == 200:
                            video_data = await resp.json()
                            return {
                                'video_id': video_id,
                                'title': video_data.get('title', 'Unknown Title'),
                                'duration': video_data.get('duration', 0),
                                'instance': instance,
                                'data': video_data
                            }
                else:
                    # Search for video
                    search_query = urllib.parse.quote(query)
                    search_url = f"{instance}/api/v1/search?q={search_query}&type=video"
                    async with session.get(search_url) as resp:
                        if resp.status == 200:
                            search_data = await resp.json()
                            if search_data and len(search_data) > 0:
                                # Find the first actual video (not playlist, channel, etc.)
                                video = None
                                for item in search_data:
                                    if item.get('type') == 'video':
                                        video = item
                                        break
                                if not video and len(search_data) > 0:
                                    video = search_data[0]
                                
                                if video:
                                    return {
                                        'video_id': video['videoId'],
                                        'title': video.get('title', 'Unknown Title'),
                                        'duration': video.get('duration', 0),
                                        'instance': instance,
                                        'data': video
                                    }
        except Exception as e:
            print(f"❌ Instance {instance} failed: {str(e)[:100]}...")
            continue
    
    return None

# Get audio URL from video data
async def get_audio_url(video_info):
    """Get audio URL from video information"""
    if not video_info:
        return None
    
    instance = video_info['instance']
    video_id = video_info['video_id']
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            video_url = f"{instance}/api/v1/videos/{video_id}"
            async with session.get(video_url) as resp:
                if resp.status == 200:
                    video_data = await resp.json()
                    
                    # Try different methods to get audio URL
                    
                    # Method 1: Look for adaptive formats (best quality)
                    best_audio = None
                    for stream in video_data.get('adaptiveFormats', []):
                        if 'audio' in stream.get('type', '') and stream.get('url'):
                            current_bitrate = stream.get('bitrate', 0)
                            if not best_audio or current_bitrate > best_audio.get('bitrate', 0):
                                best_audio = stream
                    
                    if best_audio:
                        return {
                            'url': best_audio['url'],
                            'title': video_data.get('title', video_info['title']),
                            'duration': video_data.get('duration', video_info['duration']),
                            'webpage_url': f"https://youtube.com/watch?v={video_id}",
                            'instance': instance
                        }
                    
                    # Method 2: Look for format streams
                    for stream in video_data.get('formatStreams', []):
                        if stream.get('url'):
                            return {
                                'url': stream['url'],
                                'title': video_data.get('title', video_info['title']),
                                'duration': video_data.get('duration', video_info['duration']),
                                'webpage_url': f"https://youtube.com/watch?v={video_id}",
                                'instance': instance
                            }
                    
                    # Method 3: Try to construct URL manually
                    manual_url = f"{instance}/latest_version?id={video_id}&itag=251&local=true"
                    return {
                        'url': manual_url,
                        'title': video_data.get('title', video_info['title']),
                        'duration': video_data.get('duration', video_info['duration']),
                        'webpage_url': f"https://youtube.com/watch?v={video_id}",
                        'instance': instance
                    }
                    
    except Exception as e:
        print(f"❌ Failed to get audio from {instance}: {e}")
    
    return None

# Main function to get YouTube audio
async def get_youtube_audio(query):
    """Main function to get YouTube audio using Invidious"""
    print(f"🎵 Searching for: {query}")
    
    # Step 1: Search for video
    video_info = await search_invidious_video(query)
    if not video_info:
        raise Exception("ไม่พบวิดีโอที่ค้นหา")
    
    print(f"✅ Found video: {video_info['title']}")
    
    # Step 2: Get audio URL
    audio_info = await get_audio_url(video_info)
    if not audio_info:
        raise Exception("ไม่พบสตรีมเสียงสำหรับวิดีโอนี้")
    
    print(f"✅ Found audio stream from {audio_info['instance']}")
    return audio_info

# Audio source class for Invidious
class InvidiousSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')

    @classmethod
    async def from_query(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        data = await get_youtube_audio(query)
        
        if not data:
            raise Exception("ไม่สามารถดึงข้อมูลเพลงได้")
        
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
    print(f'✅ Using Invidious only (no yt-dlp)')
    
    # Test instances on startup
    working_instances = await get_tested_instances()
    print(f'✅ {len(working_instances)} Invidious instances are working')
    
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
    """เล่นเพลงจาก YouTube ผ่าน Invidious"""
    if not ctx.author.voice:
        embed = create_embed("❌ ข้อผิดพลาด", "คุณต้องอยู่ในช่องเสียงก่อน!", 0xff0000)
        await ctx.send(embed=embed)
        return
    
    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()
    
    async with ctx.typing():
        try:
            player = await InvidiousSource.from_query(query, loop=bot.loop)
            
            if player:
                if not ctx.voice_client.is_playing():
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
            print(f"❌ Error: {error_msg}")
            
            # More specific error messages
            if "ไม่พบวิดีโอที่ค้นหา" in error_msg:
                error_detail = "Invidious instances อาจมีปัญหา ช่วงนี้ลองใช้ลิงก์ YouTube โดยตรงแทนการค้นหาชื่อเพลง"
            elif "ไม่พบสตรีมเสียง" in error_msg:
                error_detail = "วิดีโอนี้อาจมีการจำกัดการเข้าถึง หรือรูปแบบไม่รองรับ"
            else:
                error_detail = "อาจเกิดจากปัญหาชั่วคราวกับเซิร์ฟเวอร์เพลง"
            
            embed = create_embed("❌ เกิดข้อผิดพลาด", 
                f"ไม่สามารถเล่นเพลงได้\n\n"
                f"**สาเหตุ:** {error_msg}\n"
                f"**คำแนะนำ:** {error_detail}\n\n"
                f"**โปรดลอง:**\n"
                f"• ใช้ลิงก์ YouTube โดยตรงแทนการค้นหา\n"
                f"• ลองเพลงอื่น\n"
                f"• รอสักครู่แล้วลองใหม่", 0xff0000)
            await ctx.send(embed=embed)

@bot.command()
async def status(ctx):
    """แสดงสถานะบอท"""
    instances = await get_tested_instances()
    total_instances = len(await get_working_invidious_instances())
    
    embed = create_embed("📊 สถานะบอท", 
        f"**แหล่งข้อมูล:** Invidious เท่านั้น\n"
        f"**Invidious instances:** {len(instances)}/{total_instances} ทำงานได้\n"
        f"**เซิร์ฟเวอร์:** {len(bot.guilds)}\n"
        f"**พิง:** {round(bot.latency * 1000)}ms\n"
        f"**คิวเพลง:** {sum(len(q) for q in queues.values())} เพลง", 0x0099ff)
    await ctx.send(embed=embed)

@bot.command()
async def instances(ctx):
    """แสดง Invidious instances ที่ใช้งานได้"""
    instances = await get_tested_instances()
    total_instances = len(await get_working_invidious_instances())
    
    if instances:
        instances_list = "\n".join([f"• ✅ {instance}" for instance in instances[:8]])
    else:
        instances_list = "• ❌ ไม่มี instances ที่ทำงานได้ในขณะนี้"
    
    embed = create_embed("🌐 Invidious Instances", 
                        f"**สถานะ:** {len(instances)}/{total_instances} instances ทำงานได้\n\n{instances_list}", 
                        0x0099ff)
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
        if hasattr(ctx.voice_client.source, 'title'):
            title = ctx.voice_client.source.title
        else:
            title = "Unknown Title"
            
        embed = create_embed("🎵 กำลังเล่นอยู่", 
                            f"**{title}**\n\nใช้ `!queue` เพื่อดูคิวเพลง", 0x00ff00)
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
`!instances` - แสดง Invidious instances

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
        print("✅ ใช้ Invidious เท่านั้น (ไม่ใช้ yt-dlp)")
        bot.run(token)
