import os
import asyncio
from datetime import datetime
from telethon.sync import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon import events
from telethon.tl.types import MessageEntityCustomEmoji

# Configuration
API_ID = 29533823
API_HASH = '10b6a27b83b3e90aca70de60c4bd7013'
PHONE_NUMBER = '+8801747997105'
BOT_TOKEN = '7881140222:AAF6qLrvpaw6xF2NSlawGLr8y-ZDcnc3eSY'
AUTHORIZED_CHAT_IDS = [7384747527]  # Your chat ID

class BroadcastBot:
    def __init__(self):
        self.session_files = {
            'user': 'user_session.session',
            'bot': 'bot_session.session'
        }
        self.cleanup_sessions()
        
        self.user_client = None
        self.bot_client = None
        self.broadcast_active = False
        self.stop_requested = False
        self.current_message = None
        self.current_media = None
        self.current_entities = None
        self.delay_seconds = 15
        self.successful = []
        self.failed = []
        self.me = None
        self.current_flood_wait = 0
        self.last_command_time = {}
        self.cooldown = 5
        self.admins = AUTHORIZED_CHAT_IDS.copy()
        self.owner_id = AUTHORIZED_CHAT_IDS[0]

    def cleanup_sessions(self):
        """Clean up old session files"""
        for session in self.session_files.values():
            if os.path.exists(session):
                try:
                    os.remove(session)
                except:
                    pass

    def is_authorized(self, chat_id):
        """Check if user is authorized"""
        return chat_id in self.admins

    async def safe_send(self, target, message=None, file=None, entities=None):
        """Send message with flood control"""
        try:
            if file:
                await self.user_client.send_file(
                    target, 
                    file, 
                    caption=message,
                    parse_mode='html',
                    formatting_entities=entities
                )
            else:
                await self.user_client.send_message(
                    target,
                    message,
                    parse_mode='html',
                    formatting_entities=entities
                )
            return True
        except FloodWaitError as e:
            wait = e.seconds
            print(f"Flood wait: {wait} seconds")
            self.current_flood_wait = wait
            await asyncio.sleep(wait)
            return await self.safe_send(target, message, file, entities)
        except Exception as e:
            print(f"Send error: {e}")
            return False

    async def initialize(self):
        """Initialize the bot"""
        print("Starting Premium Broadcast Bot... ✨")
        
        try:
            # Initialize user client
            self.user_client = TelegramClient(
                self.session_files['user'], 
                API_ID, 
                API_HASH
            )
            await self.user_client.start(phone=PHONE_NUMBER)
            
            self.me = await self.user_client.get_me()
            print(f"User connected: {self.me.first_name}")
            
            # Initialize bot client
            self.bot_client = TelegramClient(
                self.session_files['bot'],
                API_ID,
                API_HASH
            )
            await self.bot_client.start(bot_token=BOT_TOKEN)
            
            self.setup_handlers()
            print("Bot is ready. Send /start to begin. ✨")
            await self.bot_client.run_until_disconnected()
            
        except Exception as e:
            print(f"Fatal error: {e}")
            await self.safe_shutdown()

    async def safe_shutdown(self):
        """Proper shutdown procedure"""
        try:
            if self.user_client:
                await self.user_client.disconnect()
            if self.bot_client:
                await self.bot_client.disconnect()
        except Exception as e:
            print(f"Shutdown error: {e}")

    def check_cooldown(self, user_id):
        """Prevent command spamming"""
        now = datetime.now().timestamp()
        if user_id in self.last_command_time:
            if now - self.last_command_time[user_id] < self.cooldown:
                return True
        self.last_command_time[user_id] = now
        return False

    def setup_handlers(self):
        """Setup all command handlers"""
        
        @self.bot_client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            if not self.is_authorized(event.sender_id):
                await event.respond("❌ You are not authorized! ✨")
                return
                
            if self.check_cooldown(event.sender_id):
                return
                
            await event.respond(
                "𝐌𝐄𝐍𝐔 𝐎𝐅 𝐑𝐃𝐇 𝐓𝐄𝐋𝐄𝐆𝐑𝐀𝐌 𝐁𝐎𝐓\n\n"
                "1. Send your message (text/media)\n"
                "2. Use /send to broadcast\n\n"
                "📜 Commands:\n"
                "/start - Show this help\n"
                "/send - Start broadcast\n"
                "/stop - Cancel broadcast\n"
                "/status - Check progress\n"
                "/addadmin [ID] - Add new admin\n"
                "/removeadmin [ID] - Remove admin\n"
                "/listadmins - Show all admins\n\n"
                "⚠WAIT ATLEAST 2-5 SECONDS"
            )

        @self.bot_client.on(events.NewMessage(pattern='/addadmin'))
        async def add_admin_handler(event):
            if not self.is_authorized(event.sender_id):
                return
                
            if event.sender_id != self.owner_id:
                await event.respond("❌ Only owner can add admins! ✨")
                return
                
            try:
                args = event.message.text.split()
                if len(args) < 2:
                    await event.respond("Usage: /addadmin [user_id] ✨")
                    return
                    
                new_admin = int(args[1])
                if new_admin not in self.admins:
                    self.admins.append(new_admin)
                    await event.respond(f"✅ Added admin with ID: {new_admin} ✨✨✨")
                    print(f"New admin added: {new_admin}")
                else:
                    await event.respond("ℹ User is already an admin ✨")
            except (IndexError, ValueError):
                await event.respond("Usage: /addadmin [user_id] ✨")

        @self.bot_client.on(events.NewMessage(pattern='/removeadmin'))
        async def remove_admin_handler(event):
            if not self.is_authorized(event.sender_id):
                return
                
            if event.sender_id != self.owner_id:
                await event.respond("❌ Only owner can remove admins! ✨")
                return
                
            try:
                args = event.message.text.split()
                if len(args) < 2:
                    await event.respond("Usage: /removeadmin [user_id]")
                    return
                    
                admin_to_remove = int(args[1])
                if admin_to_remove in self.admins:
                    if admin_to_remove == self.owner_id:
                        await event.respond("❌ Cannot remove the owner! ✨")
                    else:
                        self.admins.remove(admin_to_remove)
                        await event.respond(f"✅ Removed admin with ID: {admin_to_remove}")
                        print(f"Admin removed: {admin_to_remove}")
                else:
                    await event.respond("ℹ User is not an admin")
            except (IndexError, ValueError):
                await event.respond("Usage: /removeadmin [user_id]")

        @self.bot_client.on(events.NewMessage(pattern='/listadmins'))
        async def list_admins_handler(event):
            if not self.is_authorized(event.sender_id):
                return
                
            admins_list = "\n".join([f"👉 {admin_id}" for admin_id in self.admins])
            await event.respond(
                f"👑 Owner: {self.owner_id}\n"
                f"🛡 Admins:\n{admins_list}\n"
                f"Total: {len(self.admins)} admins ✨"
            )

        @self.bot_client.on(events.NewMessage(pattern='/send'))
        async def send_handler(event):
            if not self.is_authorized(event.sender_id):
                return
                
            if self.check_cooldown(event.sender_id):
                return
                
            if not self.current_message and not self.current_media:
                await event.respond("❌ No message set! Send me your message first ✨")
                return
                
            if self.broadcast_active:
                await event.respond("⚠ Broadcast already in progress! ✨")
                return
                
            self.broadcast_active = True
            self.stop_requested = False
            self.successful = []
            self.failed = []
            
            await event.respond("🚀 Starting broadcast... ✨✨✨")
            asyncio.create_task(self.run_broadcast(event.chat_id))

        @self.bot_client.on(events.NewMessage(pattern='/stop'))
        async def stop_handler(event):
            if not self.is_authorized(event.sender_id):
                return
                
            if not self.broadcast_active:
                await event.respond("⚠ No active broadcast to stop")
                return
                
            self.stop_requested = True
            await event.respond("ᴄᴜʀʀᴇɴᴛ ʙʀᴏᴀᴅᴄᴀꜱᴛ ɪꜱ ꜱᴛᴏᴘᴇᴅ 🛑 ʙʏ ᴛʜᴇ ᴜꜱᴇʀ")

        @self.bot_client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            if not self.is_authorized(event.sender_id):
                return
                
            status = "📊 Current Status \n\n"
            
            if self.broadcast_active:
                status += "🟢 Broadcast running\n"
            else:
                status += "🔴 No active broadcast\n"
                
            if self.current_flood_wait > 0:
                status += f"⏳ Waiting {self.current_flood_wait}s (flood control)\n"
                
            if self.current_message or self.current_media:
                status += "\nꜱᴇɴᴅɪɴɢ ᴛᴏ ᴄʜᴀᴛꜱ\n"
                if self.current_message:
                    status += f"𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐓𝐎 𝐒𝐄𝐍𝐃 : {self.current_message[:50]}...\n"
                if self.current_media:
                    status += "📷 Media attached\n"
            
            status += f"\n• ᴅᴏɴᴇ : {len(self.successful)}"
            status += f"\n• ꜰᴀɪʟ : {len(self.failed)}"
            
            await event.respond(status)

        @self.bot_client.on(events.NewMessage())
        async def message_handler(event):
            if not self.is_authorized(event.sender_id):
                return
                
            if event.raw_text.startswith('/'):
                return
                
            self.current_message = event.message.message
            self.current_media = event.message.media
            self.current_entities = event.message.entities
            
            preview = "✅ Message saved!\n"
            if self.current_message:
                preview += f"Text: {self.current_message[:100]}\n"
            if self.current_media:
                preview += "📷 Media attached\n"
            
            has_premium_emoji = any(
                isinstance(e, MessageEntityCustomEmoji) 
                for e in (self.current_entities or [])
            )
            
            if has_premium_emoji:
                preview += "✨ Premium emojis detected!\n"
            
            preview += "\nUse /send to broadcast"
            await event.respond(preview)

    async def run_broadcast(self, report_chat_id):
        """Execute the broadcast"""
        try:
            dialogs = await self.get_valid_chats()
            total = len(dialogs)
            
            await self.bot_client.send_message(
                report_chat_id, 
                f"ꜰᴇᴛᴄʜɪɴɢ ᴀʟʟ ᴄʜᴀᴛꜱ ᴛᴏ ꜱᴛᴀʀᴛ ʙʀᴏᴀᴅᴄᴀꜱᴛ 📤"
            )
            
            for i, dialog in enumerate(dialogs, 1):
                if not self.broadcast_active or self.stop_requested:
                    await self.bot_client.send_message(
                        report_chat_id,
                        "ꜱᴛᴏᴘᴘɪɴɢ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴘʀᴏᴄᴇꜱꜱ"
                    )
                    break
                    
                chat = dialog.entity
                chat_name = chat.title if hasattr(chat, 'title') else chat.first_name
                
                try:
                    success = await self.safe_send(
                        chat.id,
                        self.current_message,
                        self.current_media,
                        self.current_entities
                    )
                    
                    if success:
                        self.successful.append(chat_name)
                    else:
                        self.failed.append((chat_name, "Send failed"))
                    
                    if i % 5 == 0 or i == total:
                        await self.bot_client.send_message(
                            report_chat_id,
                            f"ᴘʀᴏᴄᴇꜱꜱɪɴɢ : {i}/{total}\n"
                            f"• ᴅᴏɴᴇ : {len(self.successful)}\n"
                            f"• ꜰᴀɪʟ : {len(self.failed)}"
                        )
                    
                    await asyncio.sleep(self.delay_seconds)
                
                except Exception as e:
                    self.failed.append((chat_name, str(e)))
                    continue
            
            if self.broadcast_active and not self.stop_requested:
                await self.bot_client.send_message(
                    report_chat_id,
                    f"ᴍᴇꜱꜱᴀɢᴇ ꜱᴇɴᴛ 📤\n"
                    f"• ᴅᴏɴᴇ : {len(self.successful)}\n"
                    f"• ꜰᴀɪʟ : {len(self.failed)}"
                )
                
        except Exception as e:
            print(f"Broadcast error: {e}")
            await self.bot_client.send_message(
                report_chat_id,
                f"❌ Broadcast failed: {str(e)[:200]}"
            )
        finally:
            self.broadcast_active = False
            self.stop_requested = False
            self.current_flood_wait = 0

    async def get_valid_chats(self):
        valid_chats = []
        async for dialog in self.user_client.iter_dialogs():
            if dialog.is_user:
                if dialog.entity.bot or dialog.entity.id == self.me.id:
                    continue
            valid_chats.append(dialog)
        return valid_chats

if __name__ == '__main__':
    os.system('clear')
    print("𝗦𝗧𝗔𝗥𝗧𝗜𝗡𝗚 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗕𝗢𝗧 ")
    
    bot = BroadcastBot()
    try:
        asyncio.run(bot.initialize())
    except KeyboardInterrupt:
        print("\nᴄᴜʀʀᴇɴᴛ ʙʀᴏᴀᴅᴄᴀꜱᴛ ɪꜱ ꜱᴛᴏᴘᴇᴅ 🛑 ʙʏ ᴛʜᴇ ᴜꜱᴇʀ")
    except Exception as e:
        print(f"Fatal error: {e}")
