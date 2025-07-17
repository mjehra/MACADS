import os
import logging
import asyncio
from telethon import TelegramClient, errors, events
from telethon.tl.types import Channel, Chat
from telethon.tl.custom import Button
import random
import re

BOT_TOKEN = "7768959332:AAHYhsJr-y9DL2kqSmCX4NbxuF-DXxAUb3I"
ADMIN_IDS = [7655644665]
API_ID = 29938230
API_HASH = "95feafa9424ee78571f24fc742674cd5"
PHONE_NUMBER = "+923155955000"
SESSION_FILE = "user_account1.session"
SEND_INTERVAL = 5

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger("telethon").setLevel(level=logging.CRITICAL)

class TelegramBot:
    def __init__(self):
        os.system("cls" if os.name == 'nt' else "clear")
        
        self.bot = TelegramClient(
            session="bot_session",
            api_id=API_ID,
            api_hash=API_HASH
        ).start(bot_token=BOT_TOKEN)
        
        self.user_client = TelegramClient(
            session=SESSION_FILE,
            api_id=API_ID,
            api_hash=API_HASH
        )
        
        self.groups = set()
        self.running = False
        self.user = None
        self.message_to_forward = None  # Will store (chat_id, message_id)
        self.profile_photo = None
        self.authorized_users = set(ADMIN_IDS)
        self.stats = {
            'total_groups': 0,
            'successful_forwards': 0,
            'failed_forwards': 0,
            'last_forwarded_group': None,
            'original_message_views': 0,
            'original_message_link': None
        }
        self.stats_message = None
        self.user_state = {}  # To track user's current state
        self.initialized = False  # To track if user client is logged in
        
        # Register event handlers
        self.bot.add_event_handler(self.handle_start, events.NewMessage(pattern='/start'))
        self.bot.add_event_handler(self.handle_main, events.NewMessage(pattern='/main'))
        self.bot.add_event_handler(self.handle_callback, events.CallbackQuery())
        self.bot.add_event_handler(self.handle_set_message_link, events.NewMessage())
        self.bot.add_event_handler(self.handle_admin_commands, events.NewMessage(pattern='/admin'))
        self.bot.add_event_handler(self.handle_set_photo, events.NewMessage(func=lambda e: e.photo))

    async def connect_user_client(self):
        """Connect and authenticate the user client"""
        if not os.path.exists(SESSION_FILE):
            logging.info("Creating new session file")
        
        await self.user_client.connect()
        
        if not await self.user_client.is_user_authorized():
            logging.info("User not authorized. Starting login process...")
            await self.bot.send_message(ADMIN_IDS[0], "🔑 Starting login process for user account...")
            
            try:
                await self.user_client.send_code_request(PHONE_NUMBER)
                logging.info("Sent verification code")
                await self.bot.send_message(ADMIN_IDS[0], "📲 Verification code sent. Please check your Telegram app.")
                
                # Wait for code input from admin
                self.user_state[ADMIN_IDS[0]] = "awaiting_code"
                return False
            except Exception as e:
                logging.error(f"Error sending code request: {str(e)}")
                await self.bot.send_message(ADMIN_IDS[0], f"❌ Error sending code: {str(e)}")
                return False
        
        self.user = await self.user_client.get_me()
        logging.info(f"Logged in as: {self.user.username}")
        await self.bot.send_message(ADMIN_IDS[0], f"✅ Successfully logged in as: @{self.user.username}")
        self.initialized = True
        return True

    async def complete_login(self, code):
        """Complete the login process with verification code"""
        try:
            await self.user_client.sign_in(PHONE_NUMBER, code)
            self.user_client.session.save()
            self.user = await self.user_client.get_me()
            logging.info(f"Logged in as: {self.user.username}")
            await self.bot.send_message(ADMIN_IDS[0], f"✅ Successfully logged in as: @{self.user.username}")
            self.initialized = True
            return True
        except errors.SessionPasswordNeededError:
            await self.bot.send_message(ADMIN_IDS[0], "🔒 Account has 2FA. Please enter your password:")
            self.user_state[ADMIN_IDS[0]] = "awaiting_password"
            return False
        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            await self.bot.send_message(ADMIN_IDS[0], f"❌ Login failed: {str(e)}")
            return False

    async def complete_2fa(self, password):
        """Complete 2FA authentication"""
        try:
            await self.user_client.sign_in(password=password)
            self.user_client.session.save()
            self.user = await self.user_client.get_me()
            logging.info(f"Logged in as: {self.user.username}")
            await self.bot.send_message(ADMIN_IDS[0], f" Account connected successfully! [ @GODCARING ]")
            self.initialized = True
            return True
        except Exception as e:
            logging.error(f"2FA error: {str(e)}")
            await self.bot.send_message(ADMIN_IDS[0], f" 2FA failed: {str(e)}")
            return False

    async def get_all_groups(self):
        try:
            dialogs = await self.user_client.get_dialogs()
            valid_chats = []
            
            for dialog in dialogs:
                entity = dialog.entity
                
                if isinstance(entity, Chat) or (isinstance(entity, Channel) and entity.megagroup):
                    valid_chats.append({
                        'id': dialog.id,
                        'title': dialog.title,
                        'type': 'Supergroup' if isinstance(entity, Channel) else 'Group',
                        'entity': entity
                    })
            
            self.stats['total_groups'] = len(valid_chats)
            return valid_chats
        except Exception as e:
            logging.error(f"Error getting groups: {str(e)}")
            return []

    async def update_message_views(self):
        """Update the view count of the original message"""
        if not self.message_to_forward:
            return
            
        try:
            message = await self.user_client.get_messages(
                self.message_to_forward[0],
                ids=self.message_to_forward[1]
            )
            if hasattr(message, 'views'):
                self.stats['original_message_views'] = message.views
        except Exception as e:
            logging.error(f"Error updating message views: {str(e)}")

    async def forward_to_group(self, group):
        try:
            if not self.message_to_forward:
                logging.error("No message to forward")
                return None
                
            # Get the original message
            original_msg = await self.user_client.get_messages(
                self.message_to_forward[0],
                ids=self.message_to_forward[1]
            )
            
            # Forward the message
            forwarded = await self.user_client.forward_messages(
                entity=group['id'],
                messages=original_msg
            )
            
            if isinstance(forwarded, list):
                forwarded = forwarded[0]
                
            chat = group['entity']
            if hasattr(chat, 'username') and chat.username:
                message_link = f"https://t.me/{chat.username}/{forwarded.id}"
            else:
                message_link = f"https://t.me/c/{abs(group['id'])}/{forwarded.id}"
            
            # Update message views
            await self.update_message_views()
            
            logging.info(f"Message forwarded to {group['title']}")
            self.stats['successful_forwards'] += 1
            self.stats['last_forwarded_group'] = group['title']
            return message_link
            
        except errors.FloodWaitError as e:
            logging.info(f"Flood wait: {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return await self.forward_to_group(group)
        except Exception as e:
            logging.error(f"Error forwarding to {group['title']}: {str(e)}")
            self.stats['failed_forwards'] += 1
            return None

    async def update_stats_message(self):
        if not self.stats_message:
            return
            
        stats_text = (
            f"<b>GODCARING | LIVE STATISTICS</b>\n\n"
            f"Total Groups: {self.stats['total_groups']}\n"
            f"Successful Forwards: {self.stats['successful_forwards']}\n"
            f"Failed Forwards: {self.stats['failed_forwards']}\n"
            f"Last Forwarded To: {self.stats['last_forwarded_group'] or 'None'}\n"
            f"Original Message Views: {self.stats['original_message_views']}\n"
            f"Original Message: {self.stats['original_message_link'] or 'Not set'}\n\n"
            f"Auto-updating every 10 seconds"
        )
        
        try:
            await self.stats_message.edit(stats_text, parse_mode='html')
        except Exception as e:
            logging.error(f"Error updating stats: {str(e)}")

    async def promotion_cycle(self):
        self.running = True
        self.stats_message = await self.bot.send_message(
            ADMIN_IDS[0],
            "<b>GODCARING | INITIATING FORWARDING CYCLE</b>",
            parse_mode='html'
        )
        
        while self.running:
            groups = await self.get_all_groups()
            if not groups:
                logging.info("No groups available")
                await asyncio.sleep(SEND_INTERVAL)
                continue
                
            for group in groups:
                if not self.running:
                    break
                    
                try:
                    message_link = await self.forward_to_group(group)
                    
                    if message_link and self.profile_photo:
                        report = (
                            f"<b>GODCARING | MESSAGE FORWARD CONFIRMATION</b>\n\n"
                            f"Group: {group['title']}\n"
                            f"Type: {group['type']}\n"
                            f"Link: <a href='{message_link}'>View Forwarded Message</a>\n"
                            f"Original Views: {self.stats['original_message_views']}"
                        )
                        
                        for admin_id in ADMIN_IDS:
                            await self.bot.send_file(
                                admin_id,
                                file=self.profile_photo,
                                caption=report,
                                parse_mode='html'
                            )
                    
                    await self.update_stats_message()
                    await asyncio.sleep(SEND_INTERVAL)
                except Exception as e:
                    logging.error(f"Error processing {group.get('title', 'Unknown')}: {str(e)}")
                    
            await asyncio.sleep(10)
        
        await self.stats_message.edit(
            "<b>GODCARING | FORWARDING CYCLE COMPLETED</b>\n\n"
            f"Final Statistics:\n"
            f"Total Groups: {self.stats['total_groups']}\n"
            f"Successful Forwards: {self.stats['successful_forwards']}\n"
            f"Failed Forwards: {self.stats['failed_forwards']}\n"
            f"Final Original Message Views: {self.stats['original_message_views']}",
            parse_mode='html'
        )
        self.stats_message = None

    async def show_main_menu(self, event):
        # Clear any existing state
        self.user_state.pop(event.sender_id, None)
        
        buttons = [
            [Button.inline("Start Forwarding", b"start_bot")],
            [Button.inline("Stop Forwarding", b"stop_bot")],
            [Button.inline("View Statistics", b"status")],
            [Button.inline("Set Message Link", b"set_message_link")],
        ]
        
        if event.sender_id in ADMIN_IDS:
            buttons.extend([
                [Button.inline("Admin Settings", b"admin_settings")],
                [Button.inline("Change Profile Photo", b"change_photo")]
            ])
        
        if self.profile_photo:
            await event.respond(
                " Current Profile Photo:",
                file=self.profile_photo
            )
        
        await event.respond(
            "<b>GODCARING | MAIN MENU</b>\n\n"
            "Select an action:",
            parse_mode='html',
            buttons=buttons
        )

    async def handle_start(self, event):
        if event.sender_id not in self.authorized_users:
            return await event.reply("🚫 Unauthorized access")
            
        # First ensure we're logged in
        if not self.initialized:
            login_success = await self.connect_user_client()
            if not login_success:
                return  # We're waiting for verification code
            
            # After successful login, proceed with setup
            
        # Check if profile photo is set
        if not self.profile_photo:
            self.user_state[event.sender_id] = "awaiting_photo"
            return await event.reply(
                " Please send the profile photo you want to use for confirmations:",
                buttons=Button.inline("Cancel", b"main_menu")
            )
            
        # Check if message is set
        if not self.message_to_forward:
            self.user_state[event.sender_id] = "awaiting_message_link"
            return await event.reply(
                "🔗 Please send the link of the message you want to forward (format: https://t.me/myehra/3):",
                buttons=Button.inline("Cancel", b"main_menu")
            )
            
        # If both are set, show main menu
        await self.show_main_menu(event)

    async def handle_main(self, event):
        if event.sender_id not in self.authorized_users:
            return await event.reply("🚫 Unauthorized access")
            
        await self.show_main_menu(event)

    async def handle_set_photo(self, event):
        if event.sender_id not in self.authorized_users:
            return
            
        # Check if we're expecting a photo
        if self.user_state.get(event.sender_id) == "awaiting_photo" or event.sender_id in ADMIN_IDS:
            self.profile_photo = event.media
            self.user_state.pop(event.sender_id, None)
            
            # If this was the first setup, now ask for message
            if not self.message_to_forward:
                self.user_state[event.sender_id] = "awaiting_message_link"
                await event.reply(
                    "✅ Profile photo set successfully!\n\n"
                    "🔗 Now please send the link of the message you want to forward (format: https://t.me/myehra/3):",
                    buttons=Button.inline("Cancel", b"main_menu")
                )
            else:
                await event.reply(
                    "✅ Profile photo updated successfully!",
                    parse_mode='html'
                )
                await self.show_main_menu(event)

    async def parse_message_link(self, link):
        """Parse a Telegram message link in format https://t.me/myehra/3"""
        try:
            # Basic validation
            if not link.startswith('https://t.me/'):
                return None
                
            if link.count('/') != 4:  # https://t.me/myehra/3
                return None
                
            username_part = link.split('/')[-2]
            message_id = int(link.split('/')[-1])
            
            # Resolve username to channel ID
            entity = await self.user_client.get_entity(username_part)
            return (entity.id, message_id)
            
        except ValueError:
            logging.error("Invalid message ID in link")
            return None
        except Exception as e:
            logging.error(f"Error parsing link: {str(e)}")
            return None

    async def handle_set_message_link(self, event):
        if event.sender_id not in self.authorized_users or event.text.startswith('/'):
            return
            
        user_state = self.user_state.get(event.sender_id)
        
        # Handle verification code input
        if user_state == "awaiting_code":
            code = event.raw_text.strip()
            if not code.isdigit() or len(code) != 5:
                await event.reply("❌ Invalid code format. Please enter a 5-digit verification code.")
                return
                
            login_success = await self.complete_login(code)
            if login_success:
                await event.reply("✅ Login successful! Please send /start to continue setup.")
            return
            
        # Handle 2FA password input
        elif user_state == "awaiting_password":
            password = event.raw_text.strip()
            auth_success = await self.complete_2fa(password)
            if auth_success:
                await event.reply("✅ 2FA authentication successful! Please send /start to continue setup.")
            return
            
        # Handle message link input
        elif user_state == "awaiting_message_link":
            try:
                link = event.raw_text.strip()
                message_info = await self.parse_message_link(link)
                if not message_info:
                    await event.reply("❌ Invalid message link format. Please use format: https://t.me/myehra/3")
                    return
                    
                self.message_to_forward = message_info
                self.stats['original_message_link'] = link
                
                # Verify the message exists
                try:
                    original_msg = await self.user_client.get_messages(
                        message_info[0],
                        ids=message_info[1]
                    )
                    
                    if hasattr(original_msg, 'views'):
                        self.stats['original_message_views'] = original_msg.views
                    
                    preview = original_msg.text[:100] + "..." if original_msg.text else "[Media message]"
                except Exception as e:
                    preview = "[Could not load message preview]"
                    logging.error(f"Error getting message preview: {str(e)}")
                
                self.user_state.pop(event.sender_id, None)
                
                await event.reply(
                    f"✅ Message link set successfully!\n\n"
                    f"Preview:\n<code>{preview}</code>\n\n"
                    f"Original Views: {self.stats['original_message_views']}\n"
                    "You may now start the forwarding campaign.",
                    parse_mode='html'
                )
                
                await self.show_main_menu(event)
            except Exception as e:
                await event.reply(f"Error setting message link: {str(e)}")

    async def handle_admin_commands(self, event):
        if event.sender_id not in ADMIN_IDS:
            return await event.reply("❌ Only main admin can use this command")
            
        args = event.raw_text.split()
        
        if len(args) < 2:
            return await event.reply(
                "⚙️ <b>Admin Commands:</b>\n\n"
                "/admin add [user_id] - Add authorized user\n"
                "/admin remove [user_id] - Remove authorized user\n"
                "/admin list - Show authorized users",
                parse_mode='html'
            )
            
        command = args[1]
        
        try:
            if command == "add" and len(args) > 2:
                user_id = int(args[2])
                self.authorized_users.add(user_id)
                await event.reply(f"✅ User {user_id} added to authorized list")
                
            elif command == "remove" and len(args) > 2:
                user_id = int(args[2])
                if user_id in self.authorized_users:
                    self.authorized_users.remove(user_id)
                    await event.reply(f"✅ User {user_id} removed from authorized list")
                else:
                    await event.reply(f"❌ User {user_id} not found in authorized list")
                    
            elif command == "list":
                users_list = "\n".join(str(uid) for uid in self.authorized_users)
                await event.reply(
                    f"👥 <b>Authorized Users:</b>\n\n{users_list}",
                    parse_mode='html'
                )
                
            else:
                await event.reply("❌ Invalid command")
                
        except ValueError:
            await event.reply("❌ Invalid user ID format")

    async def handle_callback(self, event):
        if event.sender_id not in self.authorized_users:
            await event.answer("🚫 Unauthorized access", alert=True)
            return
            
        command = event.data.decode('utf-8')
        
        if command == "start_bot":
            if not self.initialized:
                await event.answer("Please complete login first", alert=True)
                return
                
            if self.running:
                await event.answer("Forwarding is already running", alert=True)
                return
                
            if not self.message_to_forward:
                await event.answer("No message link set. Please set a message link first", alert=True)
                return
                
            if not self.profile_photo:
                await event.answer("No profile photo set. Please set a photo first", alert=True)
                return
                
            try:
                self.stats = {
                    'total_groups': 0,
                    'successful_forwards': 0,
                    'failed_forwards': 0,
                    'last_forwarded_group': None,
                    'original_message_views': 0,
                    'original_message_link': self.stats['original_message_link']
                }
                
                asyncio.create_task(self.promotion_cycle())
                
                await event.edit(
                    "<b>GODCARING | FORWARDING INITIATED</b>\n\n"
                    f"Original Message: {self.stats['original_message_link']}\n"
                    f"Initial Views: {self.stats['original_message_views']}\n"
                    f"Interval: {SEND_INTERVAL} seconds\n\n"
                    "You will receive live statistics shortly.",
                    parse_mode='html',
                    buttons=Button.inline("Back to Menu", b"main_menu")
                )
            except Exception as e:
                await event.answer(f"Error: {str(e)}", alert=True)
                
        elif command == "stop_bot":
            if not self.running:
                await event.answer("No active forwarding running", alert=True)
                return
                
            self.running = False
            await event.edit(
                "<b>GODCARING | FORWARDING TERMINATED</b>",
                parse_mode='html',
                buttons=Button.inline("Back to Menu", b"main_menu")
            )
            
        elif command == "status":
            status = "ACTIVE" if self.running else "INACTIVE"
            
            status_message = (
                f"<b>GODCARING | FORWARDING STATUS</b>\n\n"
                f"Status: {status}\n"
                f"Original Message: {self.stats['original_message_link'] or 'Not set'}\n"
                f"Original Views: {self.stats['original_message_views']}\n"
                f"Profile Photo: {'SET' if self.profile_photo else 'NOT SET'}\n"
            )
            
            if self.message_to_forward:
                try:
                    original_msg = await self.user_client.get_messages(
                        self.message_to_forward[0],
                        ids=self.message_to_forward[1]
                    )
                    preview = original_msg.text[:100] + "..." if original_msg.text else "[Media message]"
                except:
                    preview = "[Could not load message]"
                
                status_message += f"\nPreview:\n<code>{preview}</code>"
            
            await event.edit(
                status_message,
                parse_mode='html',
                buttons=Button.inline("Back to Menu", b"main_menu")
            )
            
        elif command == "set_message_link":
            if not self.initialized:
                await event.answer("Please complete login first", alert=True)
                return
                
            self.user_state[event.sender_id] = "awaiting_message_link"
            await event.edit(
                "🔗 Please send the link of the message you want to forward (format: https://t.me/myehra/3):",
                buttons=Button.inline("Cancel", b"main_menu")
            )
            
        elif command == "main_menu":
            await self.show_main_menu(event)
            
        elif command == "admin_settings":
            if event.sender_id not in ADMIN_IDS:
                await event.answer("Only main admin can access these settings", alert=True)
                return
                
            buttons = [
                [Button.inline("Add User", b"add_user")],
                [Button.inline("Remove User", b"remove_user")],
                [Button.inline("List Users", b"list_users")],
                [Button.inline("Back to Menu", b"main_menu")]
            ]
            
            await event.edit(
                "<b>ADMIN SETTINGS</b>\n\n"
                "Manage authorized users for this bot:",
                parse_mode='html',
                buttons=buttons
            )
            
        elif command == "change_photo":
            if event.sender_id not in ADMIN_IDS:
                await event.answer("Only admin can change photo", alert=True)
                return
                
            self.user_state[event.sender_id] = "awaiting_photo"
            await event.edit(
                "📸 Send me a new profile photo:",
                buttons=Button.inline("Cancel", b"main_menu")
            )
            
        elif command == "add_user":
            await event.edit(
                "Send the user ID to add as authorized:\n"
                "(Reply to this message with /admin add [user_id])",
                buttons=Button.inline("Back to Admin", b"admin_settings")
            )
            
        elif command == "remove_user":
            await event.edit(
                "Send the user ID to remove from authorized:\n"
                "(Reply to this message with /admin remove [user_id])",
                buttons=Button.inline("Back to Admin", b"admin_settings")
            )
            
        elif command == "list_users":
            users_list = "\n".join(str(uid) for uid in self.authorized_users)
            await event.edit(
                f"<b>Authorized Users:</b>\n\n{users_list}",
                parse_mode='html',
                buttons=Button.inline("Back to Admin", b"admin_settings")
            )
            
        await event.answer()

    async def run(self):
        await self.bot.start()
        logging.info("@GODSERVICEBOT is operational")
        await self.bot.run_until_disconnected()

if __name__ == "__main__":
    bot = TelegramBot()
    try:
        asyncio.get_event_loop().run_until_complete(bot.run())
    except KeyboardInterrupt:
        logging.info("Service terminated")
    except Exception as e:
        logging.error(f"System error: {str(e)}")
