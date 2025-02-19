import discord
from discord.ext import commands
from discord import app_commands
import os, json, asyncio, googletrans
from Func_SQL.funcSQL_utils import fetch_text_channel, check_text_channel
from Func_SQL.funcSQL_categories import allocate_category, fetch_category_allocation, fetch_all_category_allocations

class GameConfig(commands.Cog):
    """Game configuration and administration commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.BASE_DIR = "Guilds"
        if not os.path.exists(self.BASE_DIR):
            os.mkdir(self.BASE_DIR)
    
    # ─── Server Config Utilities ─────────────────────────────────────────────
    def get_server_folder(self, server_id: int) -> str:
        folder = os.path.join(self.BASE_DIR, str(server_id))
        if not os.path.exists(folder):
            os.makedirs(folder)
        return folder

    def get_server_config_path(self, server_id: int) -> str:
        return os.path.join(self.get_server_folder(server_id), "config.json")

    def load_server_config(self, server_id: int) -> dict:
        path = self.get_server_config_path(server_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"Error loading config for server {server_id}: {e}")
                config = {}
        else:
            config = {}
        if "guildes" not in config:
            config["guildes"] = {}
        if "languages" not in config:
            config["languages"] = {}
        return config

    def save_server_config(self, server_id: int, config: dict):
        path = self.get_server_config_path(server_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    def generate_prefix(self, name: str, existing_prefixes: list) -> str:
        words = name.split()
        initials = "".join([w[0].upper() for w in words if w])
        if len(initials) >= 3:
            prefix = initials[:3]
        else:
            prefix = initials.ljust(3, 'X')
        if prefix not in existing_prefixes:
            return prefix
        base = prefix[:2]
        for digit in range(1, 10):
            new_prefix = f"{base}{digit}"
            if new_prefix not in existing_prefixes:
                return new_prefix
        return prefix + "0"

    # ─── Backup Utilities ─────────────────────────────────────────────────────
    def backup_channel_permissions(self, guild: discord.Guild) -> dict:
        backup = {}
        for channel in guild.channels:
            overwrites_data = {}
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Role):
                    target_type = "role"
                elif isinstance(target, discord.Member):
                    target_type = "member"
                else:
                    target_type = "unknown"
                overwrites_data[str(target.id)] = {
                    "target_type": target_type,
                    "permissions": overwrite._values  # Use with caution
                }
            backup[str(channel.id)] = overwrites_data
        return backup

    def save_backup(self, server_id: int, backup_data: dict):
        path = os.path.join(self.get_server_folder(server_id), "permissions_backup.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, indent=4)

    def load_backup(self, server_id: int) -> dict:
        path = os.path.join(self.get_server_folder(server_id), "permissions_backup.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    # ─── Autocompletion Functions ────────────────────────────────────────────
    async def language_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        for code, name in googletrans.LANGUAGES.items():
            if current.lower() in code.lower() or current.lower() in name.lower():
                choices.append(app_commands.Choice(name=f"{name.title()} ({code.upper()})", value=code.upper()))
        return choices[:25]

    async def cat_name_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        if interaction.guild:
            for cat in interaction.guild.categories:
                display_name = f"{cat.name} (ID: {cat.id})"
                if current.lower() in cat.name.lower():
                    choices.append(app_commands.Choice(name=display_name, value=str(cat.id)))
        return choices[:25]

    async def guilde_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        config = self.load_server_config(interaction.guild_id)
        game_guilds = config.get("guildes", {})
        for gg_id, gg in game_guilds.items():
            base_prefix = gg.get("base_prefix", "")
            name = gg.get("name", "")
            if current.lower() in base_prefix.lower() or current.lower() in name.lower():
                display = f"{name} ({base_prefix})"
                choices.append(app_commands.Choice(name=display, value=base_prefix))
        return choices[:25]

    # ─── Slash Commands ───────────────────────────────────────────────────────
    @app_commands.command(name="guild_add", description="Add a new game guild (max 10 per server)")
    async def guild_add(self, interaction: discord.Interaction, name: str):
        server_id = interaction.guild_id
        guild = interaction.guild
        config = self.load_server_config(server_id)
        guildes = config.get("guildes", {})
        if len(guildes) >= 10:
            await interaction.response.send_message("⚠️ Maximum number of game guilds reached (10).", ephemeral=True)
            return
        if not guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ I do not have permission to create roles.\n"
                "👉 Ensure I have the 'Manage Roles' permission and that my role is above those to be created.\n"
                "⚙️ Please adjust your server settings accordingly.",
                ephemeral=True
            )
            return
        existing_prefixes = [g.get("base_prefix") for g in guildes.values()]
        base_prefix = self.generate_prefix(name, existing_prefixes)
        new_id = 1
        existing_ids = [int(g_id) for g_id in guildes.keys() if g_id.isdigit()]
        while new_id in existing_ids:
            new_id += 1
        guild_config = {"id": new_id, "name": name, "base_prefix": base_prefix}
        config["guildes"][str(new_id)] = guild_config
        self.save_server_config(server_id, config)
        # Create roles for each configured language
        for lang_code in config.get("languages", {}):
            full_prefix = f"{base_prefix}_{lang_code}"
            role_name = f"Role_{full_prefix}"
            existing_role = discord.utils.get(guild.roles, name=role_name)
            if existing_role is None:
                try:
                    await guild.create_role(name=role_name)
                except Exception as e:
                    print(f"Error creating role {role_name}: {e}")
        await interaction.response.send_message(
            f"✅ Game guild added with ID **{new_id}** and base prefix **{base_prefix}**.",
            ephemeral=True
        )

    @app_commands.command(name="config_show", description="Display the current server configuration")
    async def config_show(self, interaction: discord.Interaction):
        server_id = interaction.guild_id
        config = self.load_server_config(server_id)
        game_guilds = config.get("guildes", {})
        global_languages = config.get("languages", {})
        message = "**🛠 Server Configuration**\n\n"
        message += "**📚 Game Guilds:**\n"
        if game_guilds:
            for gg_id, gg in game_guilds.items():
                message += f"• **ID {gg_id}** | Name: *{gg.get('name', 'N/A')}* | Base Prefix: **{gg.get('base_prefix', 'N/A')}**\n"
        else:
            message += "• No game guilds configured.\n"
        message += "\n**🌐 Configured Languages:**\n"
        if global_languages:
            for code, name in global_languages.items():
                message += f"• **{name}** ({code})\n"
        else:
            message += "• No languages configured.\n"
        message += "\n**🗂 Allocated Categories:**\n"
        allocations = await fetch_all_category_allocations(server_id)
        if allocations:
            for alloc in allocations:
                category_id, category_name, allocated_game_guild_id, allocated_game_guild = alloc
                message += f"• **Category**: *{category_name}* (ID: {category_id})\n"
                message += f"  ↳ Allocated to: **{allocated_game_guild}** (ID: {allocated_game_guild_id})\n"
        else:
            message += "• No allocated categories.\n"
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="cat_allocate", description="Allocate a category to a game guild")
    @app_commands.autocomplete(cat_id=cat_name_autocomplete, guilde=guilde_autocomplete)
    @app_commands.describe(cat_id="Category ID", guilde="Game guild (Base Prefix or Name)")
    async def cat_allocate(self, interaction: discord.Interaction, cat_id: str, guilde: str):
        if interaction.guild is None:
            await interaction.response.send_message("⚠️ This command can only be used in a server.", ephemeral=True)
            return
        guild_obj = interaction.guild
        guild_id = guild_obj.id
        category = None
        for cat in guild_obj.categories:
            if str(cat.id) == cat_id:
                category = cat
                break
        if category is None:
            await interaction.response.send_message(f"❌ Category with ID {cat_id} not found.", ephemeral=True)
            return
        config = self.load_server_config(guild_id)
        game_guilds = config.get("guildes", {})
        allocated_game_guild_id = None
        allocated_game_guild = None
        for gg_id, gg_config in game_guilds.items():
            if gg_config.get("base_prefix", "").lower() == guilde.lower() or gg_config.get("name", "").lower() == guilde.lower():
                allocated_game_guild_id = int(gg_id)
                allocated_game_guild = gg_config
                break
        if allocated_game_guild_id is None:
            await interaction.response.send_message(f"❌ Game guild '{guilde}' not found.", ephemeral=True)
            return
        try:
            await allocate_category(category.id, guild_id, category.name, allocated_game_guild_id, allocated_game_guild.get("base_prefix", ""))
            await interaction.response.send_message(
                f"✅ Category **{category.name}** has been allocated to game guild **{allocated_game_guild.get('name', guilde)}**.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error during allocation: {e}", ephemeral=True)

    @app_commands.command(name="guild_list", description="Display the list of game guilds configured on this server")
    async def guild_list(self, interaction: discord.Interaction):
        server_id = interaction.guild_id
        config = self.load_server_config(server_id)
        guildes = config.get("guildes", {})
        if not guildes:
            await interaction.response.send_message("ℹ️ No game guilds configured on this server.", ephemeral=True)
            return
        message = "Game Guilds List:\n"
        for g_id, g_config in guildes.items():
            message += f"• **ID {g_id}** - Name: **{g_config.get('name')}**, Base Prefix: **{g_config.get('base_prefix')}**\n"
            if config.get("languages"):
                for lang_code in config["languages"]:
                    base_prefix = g_config.get("base_prefix")
                    full_prefix = f"{base_prefix}_{lang_code}"
                    message += f"   - Language: **{lang_code}**, Full Prefix: **{full_prefix}**\n"
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="server_list_languages", description="Display the languages configured for this server")
    async def server_list_languages(self, interaction: discord.Interaction):
        server_id = interaction.guild_id
        config = self.load_server_config(server_id)
        languages = config.get("languages", {})
        if not languages:
            await interaction.response.send_message("ℹ️ No languages configured for this server.", ephemeral=True)
            return
        message = "Languages configured on this server:\n"
        for code, name in languages.items():
            message += f"• **{name} ({code})**\n"
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="sync_channels", description="Synchronize channel permissions based on DB, allocations, and language configuration")
    async def sync_channels(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        server_id = interaction.guild_id
        guild_obj = interaction.guild
        config = self.load_server_config(server_id)
        game_guilds = config.get("guildes", {})
        global_languages = config.get("languages", {})

        # Step 0: Backup permissions
        backup_data = self.backup_channel_permissions(guild_obj)
        self.save_backup(server_id, backup_data)
        print("Backup completed:", backup_data)

        # Step 1: Update languages from DB
        for channel in guild_obj.channels:
            exists = await check_text_channel(channel.id)
            if exists:
                ch_data = await fetch_text_channel(channel.id)
                short_lang = ch_data[7]  # Adjust index per your DB
                if short_lang:
                    lang_code = short_lang.upper()
                    if lang_code not in global_languages:
                        lang_full = googletrans.LANGUAGES.get(lang_code.lower(), lang_code).title()
                        global_languages[lang_code] = lang_full
        config["languages"] = global_languages
        self.save_server_config(server_id, config)

        # Step 2: Build roles mapping for each game guild
        roles_dict = {}
        for g_config in game_guilds.values():
            base_prefix = g_config.get("base_prefix")
            lang_roles = {}
            for lang_code in global_languages:
                full_prefix = f"{base_prefix}_{lang_code}"
                role_name = f"Role_{full_prefix}"
                role = discord.utils.get(guild_obj.roles, name=role_name)
                if role:
                    lang_roles[lang_code] = role
                else:
                    print(f"Role not found: {role_name}")
            roles_dict[base_prefix] = lang_roles

        restored_count = 0
        # Step 3: Apply configuration to each channel/category
        for channel in guild_obj.channels:
            channel_name = channel.name.lower()
            if isinstance(channel, discord.CategoryChannel):
                has_prefix = any(channel_name.startswith(bp.lower()) or channel_name.endswith(bp.lower()) for bp in roles_dict)
                if not has_prefix:
                    allocation = await fetch_category_allocation(channel.id, guild_obj.id)
                    if allocation:
                        allocated_game_guild = allocation[1]
                        lang_roles = roles_dict.get(allocated_game_guild, {})
                    else:
                        lang_roles = {}
                else:
                    for bp in roles_dict:
                        if channel_name.startswith(bp.lower()) or channel_name.endswith(bp.lower()):
                            lang_roles = roles_dict[bp]
                            break
                try:
                    await channel.set_permissions(guild_obj.default_role, overwrite=discord.PermissionOverwrite(view_channel=False))
                    for role in lang_roles.values():
                        await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=True))
                    if channel.overwrites:
                        for target, overw in channel.overwrites.items():
                            if isinstance(target, discord.Role) and target not in lang_roles.values() and target != guild_obj.default_role:
                                new_overwrite = overw
                                new_overwrite.view_channel = None
                                await channel.set_permissions(target, overwrite=new_overwrite)
                    restored_count += 1
                    print(f"Category {channel.name} configured.")
                except Exception as e:
                    print(f"Error configuring category {channel.name}: {e}")
            else:
                exists = await check_text_channel(channel.id)
                if exists:
                    ch_data = await fetch_text_channel(channel.id)
                    short_lang = ch_data[7]
                    if short_lang:
                        short_lang = short_lang.upper()
                        applied = False
                        for base_prefix, lang_roles in roles_dict.items():
                            bp_lower = base_prefix.lower()
                            short_lang_lower = short_lang.lower()
                            full_prefix = f"{bp_lower}_{short_lang_lower}"
                            if channel_name.startswith(full_prefix) or channel_name.endswith(full_prefix):
                                try:
                                    await channel.set_permissions(guild_obj.default_role, overwrite=discord.PermissionOverwrite(view_channel=False))
                                    for lang_code, role in lang_roles.items():
                                        if lang_code.upper() == short_lang:
                                            await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=True))
                                        else:
                                            await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=False))
                                    if channel.overwrites:
                                        for target, overw in channel.overwrites.items():
                                            if isinstance(target, discord.Role) and target not in lang_roles.values() and target != guild_obj.default_role:
                                                new_overwrite = overw
                                                new_overwrite.view_channel = None
                                                await channel.set_permissions(target, overwrite=new_overwrite)
                                    restored_count += 1
                                    applied = True
                                    print(f"Channel {channel.name} configured with complete prefix for language {short_lang}.")
                                except Exception as e:
                                    print(f"Error configuring channel {channel.name} (complete prefix): {e}")
                                break
                        if not applied and channel.category is not None:
                            allocation = await fetch_category_allocation(channel.category.id, guild_obj.id)
                            if allocation:
                                allocated_game_guild = allocation[1]
                                lang_roles = roles_dict.get(allocated_game_guild, {})
                                try:
                                    await channel.set_permissions(guild_obj.default_role, overwrite=discord.PermissionOverwrite(view_channel=False))
                                    for lang_code, role in lang_roles.items():
                                        if lang_code.upper() == short_lang:
                                            await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=True))
                                        else:
                                            await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=False))
                                    if channel.overwrites:
                                        for target, overw in channel.overwrites.items():
                                            if isinstance(target, discord.Role) and target not in lang_roles.values() and target != guild_obj.default_role:
                                                new_overwrite = overw
                                                new_overwrite.view_channel = None
                                                await channel.set_permissions(target, overwrite=new_overwrite)
                                    restored_count += 1
                                    applied = True
                                    print(f"Channel {channel.name} configured via allocated category for language {short_lang}.")
                                except Exception as e:
                                    print(f"Error configuring channel {channel.name} via allocated category: {e}")
                        if not applied:
                            matching_guild = None
                            for base_prefix, lang_roles in roles_dict.items():
                                if short_lang in (code.upper() for code in lang_roles.keys()):
                                    matching_guild = base_prefix
                                    break
                            if matching_guild:
                                try:
                                    await channel.set_permissions(guild_obj.default_role, overwrite=discord.PermissionOverwrite(view_channel=False))
                                    for lang_code, role in roles_dict[matching_guild].items():
                                        if lang_code.upper() == short_lang:
                                            await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=True))
                                        else:
                                            await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=False))
                                    if channel.overwrites:
                                        for target, overw in channel.overwrites.items():
                                            if (isinstance(target, discord.Role) and 
                                                target not in roles_dict[matching_guild].values() and 
                                                target != guild_obj.default_role):
                                                new_overwrite = overw
                                                new_overwrite.view_channel = None
                                                await channel.set_permissions(target, overwrite=new_overwrite)
                                    restored_count += 1
                                    print(f"Channel {channel.name} fallback configured for language {short_lang} (matching guild: {matching_guild}).")
                                except Exception as e:
                                    print(f"Error in fallback configuration for channel {channel.name}: {e}")
                            else:
                                print(f"No guild found for language {short_lang} in fallback for channel {channel.name}.")
                else:
                    print(f"Channel {channel.name} not configured in DB, ignored.")
        await interaction.followup.send(f"✅ Permissions synchronized for **{restored_count}** channels.", ephemeral=True)

    @app_commands.command(name="rollback", description="Restore channel permissions from the last backup")
    async def rollback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        server_id = interaction.guild_id
        guild = interaction.guild
        backup_data = self.load_backup(server_id)
        if not backup_data:
            await interaction.followup.send("ℹ️ No backup found.", ephemeral=True)
            return
        restored_channels = 0
        for channel in guild.channels:
            ch_backup = backup_data.get(str(channel.id), {})
            new_overwrites = {}
            for target_id, data in ch_backup.items():
                target_type = data.get("target_type")
                perms = data.get("permissions", {})
                if target_type == "role":
                    target = guild.get_role(int(target_id))
                elif target_type == "member":
                    target = guild.get_member(int(target_id))
                else:
                    target = None
                if target:
                    new_overwrites[target] = discord.PermissionOverwrite(**perms)
            try:
                await channel.edit(overwrites=new_overwrites)
                restored_channels += 1
            except Exception as e:
                print(f"Error restoring permissions for channel {channel.name}: {e}")
        await interaction.followup.send(f"✅ **{restored_channels}** channels restored successfully.", ephemeral=True)

    @app_commands.command(name="help", description="Display detailed help information for the bot")
    async def help(self, interaction: discord.Interaction):
        help_message = (
            "**Bot Help Information**\n\n"
            "**General Commands:**\n"
            "• `/guild_add <name>` - Add a new game guild.\n"
            "• `/config_show` - Display current server configuration.\n"
            "• `/cat_allocate <cat_id> <guilde>` - Allocate a category to a game guild.\n"
            "• `/guild_list` - List all configured game guilds.\n"
            "• `/server_list_languages` - List all languages configured for the server.\n"
            "• `/sync_channels` - Synchronize channel permissions based on the database and allocations.\n"
            "• `/rollback` - Restore channel permissions from the last backup.\n\n"
            "For further assistance, please refer to the documentation."
        )
        await interaction.response.send_message(help_message, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GameConfig(bot))
    
async def teardown(bot: commands.Bot):
    await bot.remove_cog("GameConfig")
    
async def cog_help(bot: commands.Bot):
    """Optional: A function to list all cogs and their commands."""
    for cog_name, cog in bot.cogs.items():
        print(f"{cog_name}:")
        for command in cog.get_commands():
            print(f"  - {command.name}: {command.description}")

async def teardown_all(bot: commands.Bot):
    for cog_name in list(bot.cogs.keys()):
        await bot.remove_cog(cog_name)

# End of cog
async def setup(bot: commands.Bot):
    await bot.add_cog(GameConfig(bot))
    
async def teardown(bot: commands.Bot):
    await bot.remove_cog("GameConfig")
    
# (Note: Only one 'setup' function should be exported from a cog module.)
    
