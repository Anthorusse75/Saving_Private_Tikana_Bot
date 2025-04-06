# cogs/gameconfig.py

import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import asyncio
import googletrans
import logging

from Func_SQL.funcSQL_utils import fetch_text_channel, check_text_channel
from Func_SQL.funcSQL_categories import allocate_category, fetch_category_allocation, fetch_all_category_allocations
from config import logger

# -------------------------------------------------------------------------
# Intervalle (en secondes) entre deux appels set_permissions
PERMISSION_SET_DELAY = 0.4

# -------------------------------------------------------------------------
# Permissions complètes pour le bot (vraiment tout)
# -------------------------------------------------------------------------
BOT_FULL_PERMS = discord.PermissionOverwrite(
    view_channel=True,
    manage_channels=True,
    manage_roles=True,
    manage_webhooks=True,
    create_instant_invite=True,
    send_messages=True,
    send_tts_messages=True,
    manage_messages=True,
    embed_links=True,
    attach_files=True,
    read_message_history=True,
    mention_everyone=True,
    external_emojis=True,
    add_reactions=True,
    connect=True,
    speak=True,
    stream=True,
    use_application_commands=True,
    manage_threads=True,
    create_public_threads=True,
    create_private_threads=True,
    send_messages_in_threads=True,
    use_embedded_activities=True,
    use_external_stickers=True,
    priority_speaker=True,
    request_to_speak=True
)

# -------------------------------------------------------------------------
# 2 rôles par catégorie : READ = lecture seule, WRITE = lecture + écriture
# -------------------------------------------------------------------------
READ_ONLY_PERMS = discord.PermissionOverwrite(
    read_message_history=True,
    send_messages=False
)
READ_WRITE_PERMS = discord.PermissionOverwrite(
    # Aucune gestion view_channel
    read_message_history=True,
    
    # Autres permissions "basique d'écriture"
    send_messages=True,
    attach_files=True,
    embed_links=True,
    add_reactions=True
)

# -------------------------------------------------------------------------
# "Basic perms" pour @everyone (on part de l'idée que c'est "rien du tout")
# -------------------------------------------------------------------------
EVERYONE_BASIC = discord.PermissionOverwrite(
    view_channel=False
)

# -------------------------------------------------------------------------
# Comparaison d'overwrites
# -------------------------------------------------------------------------
def needs_update(current: discord.PermissionOverwrite, new: discord.PermissionOverwrite) -> bool:
    return current._values != new._values

async def set_perms_if_needed(
    channel: discord.abc.GuildChannel,
    target: discord.abc.Snowflake,
    overwrite: discord.PermissionOverwrite,
    reason: str = None
) -> bool:
    """
    Met à jour l'overwrite pour 'target' si c'est vraiment différent.
    Retourne True si on a effectivement appelé set_permissions.
    """
    current = channel.overwrites.get(target)
    if not current:
        # Pas d'overwrite existant
        if not overwrite._values:
            return False  # rien à faire
        await channel.set_permissions(target, overwrite=overwrite, reason=reason)
        return True
    else:
        if needs_update(current, overwrite):
            await channel.set_permissions(target, overwrite=overwrite, reason=reason)
            return True
    return False

async def remove_all_overwrites_except_everyone(channel: discord.abc.GuildChannel) -> None:
    """
    Retire tous les overwrites, puis remet @everyone = EVERYONE_BASIC.
    """
    # Récupère l'@everyone
    everyone_role = channel.guild.default_role
    # On supprime tous les overwrites
    await channel.edit(overwrites={})
    # On remet "everyone" = perms basiques
    await channel.set_permissions(everyone_role, overwrite=EVERYONE_BASIC, reason="wipe overwrites except everyone")

# -------------------------------------------------------------------------
class GameConfig(commands.Cog):
    """Game configuration, admin management, and synchronization commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.BASE_DIR = "Guilds"
        os.makedirs(self.BASE_DIR, exist_ok=True)
        # Schedule the update of all server configurations on startup
        self.bot.loop.create_task(self.update_all_server_configs())

    # ─── Server Configuration Utilities ─────────────────────────────────────
    def get_server_folder(self, server_id: int) -> str:
        folder = os.path.join(self.BASE_DIR, str(server_id))
        os.makedirs(folder, exist_ok=True)
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
                logger.error(f"Error loading config for server {server_id}: {e}")
                config = {}
        else:
            config = {}
        if "guildes" not in config:
            config["guildes"] = {}
        if "languages" not in config:
            config["languages"] = {}
        if "bot_admins" not in config:
            config["bot_admins"] = []
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

    async def update_all_server_configs(self):
        """Scan and update all server config files to ensure required keys exist."""
        guilds_folder = self.BASE_DIR
        for folder in os.listdir(guilds_folder):
            config_path = os.path.join(guilds_folder, folder, "config.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception as e:
                    logger.error(f"Error reading config for guild {folder}: {e}")
                    continue
                updated = False
                if "guildes" not in config:
                    config["guildes"] = {}
                    updated = True
                if "languages" not in config:
                    config["languages"] = {}
                    updated = True
                if "bot_admins" not in config:
                    config["bot_admins"] = []
                    updated = True
                if updated:
                    try:
                        with open(config_path, "w", encoding="utf-8") as f:
                            json.dump(config, f, indent=4)
                        logger.info(f"Updated config for guild {folder}.")
                    except Exception as e:
                        logger.error(f"Error updating config for guild {folder}: {e}")

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
                    "permissions": overwrite._values
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

    # ─── Bot Admin Group Utilities ────────────────────────────────────────────
    def get_bot_admins(self, guild: discord.Guild, config: dict) -> list:
        if "bot_admins" not in config or not config["bot_admins"]:
            config["bot_admins"] = [str(guild.owner_id)]
            self.save_server_config(guild.id, config)
        return config["bot_admins"]

    def is_bot_admin(self, member: discord.Member, guild: discord.Guild, config: dict) -> bool:
        admins = self.get_bot_admins(guild, config)
        return str(member.id) in admins or member.id == guild.owner_id

    # ──────────────────────────────────────────────────────────────────────────
    # Commands
    # ──────────────────────────────────────────────────────────────────────────

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
                "👉 Ensure I have 'Manage Roles' and that my role is above the roles to be created.\n"
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
                    logger.error(f"Error creating role {role_name}: {e}")
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
        category = discord.utils.get(guild_obj.categories, id=int(cat_id))
        if not category:
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

    async def ensure_read_write_roles(self, guild: discord.Guild, category: discord.CategoryChannel):
        """
        Assure 2 rôles <CategoryName>_READ et <CategoryName>_WRITE, les crée si besoin.
        Retourne (read_role, write_role).
        """
        cat_name_sanit = category.name.replace(" ", "_")
        read_name = f"{cat_name_sanit}_READ"
        write_name = f"{cat_name_sanit}_WRITE"

        read_role = discord.utils.get(guild.roles, name=read_name)
        if not read_role:
            read_role = await guild.create_role(name=read_name)
            logger.debug(f"Création du rôle: {read_name}")

        write_role = discord.utils.get(guild.roles, name=write_name)
        if not write_role:
            write_role = await guild.create_role(name=write_name)
            logger.debug(f"Création du rôle: {write_name}")

        return read_role, write_role

    @app_commands.command(name="sync_channels", description="Synchronize channel permissions: wipe them, bot full perms, 2 roles per cat, plus short_lang logic.")
    async def sync_channels(self, interaction: discord.Interaction):
        logger.debug("===== [sync_channels] Début de la commande. =====")
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Impossible de synchroniser hors d'un serveur.", ephemeral=True)
            return

        server_id = guild.id
        logger.debug(f"[sync_channels] Guild ID = {server_id}, Name = {guild.name} — {len(guild.channels)} channels trouvés.")

        config = self.load_server_config(server_id)
        game_guilds = config.get("guildes", {})
        global_languages = config.get("languages", {})

        # Step 0 : backup
        backup_data = self.backup_channel_permissions(guild)
        self.save_backup(server_id, backup_data)
        logger.debug("[sync_channels] Backup completed OK")

        set_permissions_count = 0
        restored_count = 0

        async def maybe_sleep():
            await asyncio.sleep(PERMISSION_SET_DELAY)

        # Step 1 : Met à jour les langues depuis la DB
        for channel in guild.channels:
            exist = await check_text_channel(channel.id)
            if exist:
                ch_data = await fetch_text_channel(channel.id)
                if len(ch_data) > 7 and ch_data[7]:
                    short_lang = ch_data[7].upper()
                    if short_lang not in global_languages:
                        lang_full = googletrans.LANGUAGES.get(short_lang.lower(), short_lang).title()
                        global_languages[short_lang] = lang_full
        config["languages"] = global_languages
        self.save_server_config(server_id, config)

        # Step 2 : Build roles mapping (base_prefix -> {lang_code: role})
        roles_dict = {}
        for g_config in game_guilds.values():
            bp = g_config.get("base_prefix")
            if not bp:
                continue
            local_map = {}
            for lang_code in global_languages:
                r_name = f"Role_{bp}_{lang_code}"
                role = discord.utils.get(guild.roles, name=r_name)
                if not role:
                    try:
                        role = await guild.create_role(name=r_name)
                        logger.debug(f"Créé role {r_name}")
                    except Exception as e:
                        logger.error(f"Erreur creation role {r_name}: {e}")
                        continue
                local_map[lang_code] = role
            roles_dict[bp] = local_map

        logger.debug("[sync_channels] Roles dict complet.")

        # Step 3 : Parcours de chaque canal
        for i, channel in enumerate(guild.channels, start=1):
            logger.debug(f"[{i}/{len(guild.channels)}] Traitement du canal '{channel.name}' (ID={channel.id})")

            # 3a) Wipe total => on ne garde que @everyone basic
            await remove_all_overwrites_except_everyone(channel)
            set_permissions_count += 1
            await maybe_sleep()

            # 3b) Bot full perms
            changed = await set_perms_if_needed(channel, guild.me, BOT_FULL_PERMS, reason="bot full perms")
            if changed:
                set_permissions_count += 1
                await maybe_sleep()

            # 3c) 2 rôles par catégorie si c'est une CategoryChannel
            if isinstance(channel, discord.CategoryChannel):
                read_role, write_role = await self.ensure_read_write_roles(guild, channel)
                c1 = await set_perms_if_needed(channel, read_role, READ_ONLY_PERMS, reason="cat read role")
                if c1: set_permissions_count += 1; await maybe_sleep()
                c2 = await set_perms_if_needed(channel, write_role, READ_WRITE_PERMS, reason="cat write role")
                if c2: set_permissions_count += 1; await maybe_sleep()

                # On applique la logique “prefix/alloc/union”
                cat_name = channel.name.lower()
                has_prefix = any(cat_name.startswith(bp.lower()) or cat_name.endswith(bp.lower()) for bp in roles_dict)
                if not has_prefix:
                    # Regarde alloc DB
                    allocation = await fetch_category_allocation(channel.id, guild.id)
                    if allocation:
                        allocated_bp = allocation[1]
                        # view_channel = True pour tous les roles de ce bp
                        for r_lang in roles_dict.get(allocated_bp, {}).values():
                            c3 = await set_perms_if_needed(channel, r_lang, discord.PermissionOverwrite(view_channel=True), reason="cat alloc")
                            if c3: set_permissions_count += 1; await maybe_sleep()
                    else:
                        # union
                        union_map = {}
                        for local_map in roles_dict.values():
                            for rr in local_map.values():
                                union_map[rr.id] = rr
                        for r_lang in union_map.values():
                            c4 = await set_perms_if_needed(channel, r_lang, discord.PermissionOverwrite(view_channel=True), reason="cat union")
                            if c4: set_permissions_count += 1; await maybe_sleep()
                else:
                    # prefix => on applique
                    for bp in roles_dict:
                        if cat_name.startswith(bp.lower()) or cat_name.endswith(bp.lower()):
                            for r_lang in roles_dict[bp].values():
                                c5 = await set_perms_if_needed(channel, r_lang, discord.PermissionOverwrite(view_channel=True), reason="cat prefix")
                                if c5: set_permissions_count += 1; await maybe_sleep()
                            break

                restored_count += 1
            else:
                # 3d) Pour un TextChannel / VoiceChannel
                exist = await check_text_channel(channel.id)
                if not exist:
                    # Non configuré => union de tous les roles => view_channel=True
                    union_map = {}
                    for local_map in roles_dict.values():
                        for rr in local_map.values():
                            union_map[rr.id] = rr
                    for r_lang in union_map.values():
                        c6 = await set_perms_if_needed(channel, r_lang, discord.PermissionOverwrite(view_channel=True), reason="channel union noDB")
                        if c6: set_permissions_count += 1; await maybe_sleep()
                    logger.debug(f"Channel '{channel.name}' => non-DB => union applied.")
                    restored_count += 1
                else:
                    # canal en DB => essaye short_lang
                    ch_data = await fetch_text_channel(channel.id)
                    short_lang = ch_data[7] if len(ch_data) > 7 else None
                    if short_lang:
                        short_lang = short_lang.upper()
                        applied = False

                        # prefix complet ?
                        for bp, local_map in roles_dict.items():
                            full_prefix = f"{bp.lower()}_{short_lang.lower()}"
                            if channel.name.lower().startswith(full_prefix) or channel.name.lower().endswith(full_prefix):
                                # Applique sur ce canal
                                for lang_code, r_lang in local_map.items():
                                    # Seule la langue == short_lang => True ; sinon => False
                                    ow = (
                                        discord.PermissionOverwrite(view_channel=True)
                                        if lang_code.upper() == short_lang.upper()
                                        else discord.PermissionOverwrite(view_channel=False)
                                    )
                                    c7 = await set_perms_if_needed(channel, r_lang, ow, reason="prefix complet channel")
                                    if c7: set_permissions_count += 1
                                    await maybe_sleep()

                                restored_count += 1
                                applied = True
                                break

                        if not applied and channel.category:
                            cat_alloc = await fetch_category_allocation(channel.category.id, guild.id)
                            if cat_alloc:
                                allocated_bp = cat_alloc[1]
                                local_map = roles_dict.get(allocated_bp, {})
                                for lang_code, r_lang in local_map.items():
                                    # Seule la langue == short_lang => True
                                    ow = (
                                        discord.PermissionOverwrite(view_channel=True)
                                        if lang_code.upper() == short_lang.upper()
                                        else discord.PermissionOverwrite(view_channel=False)
                                    )
                                    c8 = await set_perms_if_needed(channel, r_lang, ow, reason="alloc cat channel")
                                    if c8: set_permissions_count += 1
                                    await maybe_sleep()

                                restored_count += 1
                                applied = True


                        if not applied:
                            matched_bp = None
                            for bp, local_map in roles_dict.items():
                                if short_lang in [lc.upper() for lc in local_map.keys()]:
                                    matched_bp = bp
                                    break
                            if matched_bp:
                                for lang_code, r_lang in roles_dict[matched_bp].items():
                                    # Seule la langue == short_lang => True ; sinon => False
                                    ow = (
                                        discord.PermissionOverwrite(view_channel=True)
                                        if lang_code.upper() == short_lang.upper()
                                        else discord.PermissionOverwrite(view_channel=False)
                                    )
                                    c9 = await set_perms_if_needed(channel, r_lang, ow, reason="fallback channel")
                                    if c9: set_permissions_count += 1
                                    await maybe_sleep()
                                restored_count += 1
                            else:
                                logger.error(f"No guild found for short_lang={short_lang} on channel {channel.name} fallback.")
                    else:
                        # short_lang = None => union
                        union_map = {}
                        for local_map in roles_dict.values():
                            for rr in local_map.values():
                                union_map[rr.id] = rr
                        for r_lang in union_map.values():
                            c10 = await set_perms_if_needed(channel, r_lang, discord.PermissionOverwrite(view_channel=True), reason="short_lang None => union")
                            if c10: set_permissions_count += 1; await maybe_sleep()
                        restored_count += 1
                        logger.debug(f"Channel '{channel.name}' => short_lang=None => union applied.")

            logger.debug(f"[{i}/{len(guild.channels)}] Fin du canal '{channel.name}'. (set_perms_count={set_permissions_count})")

        msg = f"✅ Permissions synchronized for **{restored_count}** channels.\n" \
              f"(set_permissions called {set_permissions_count} times)."
        logger.debug(msg)
        await interaction.followup.send(msg, ephemeral=True)
        logger.debug("===== [sync_channels] Fin de la commande. =====")

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
                ttype = data.get("target_type")
                perms = data.get("permissions", {})
                if ttype == "role":
                    target = guild.get_role(int(target_id))
                elif ttype == "member":
                    target = guild.get_member(int(target_id))
                else:
                    target = None
                if target:
                    new_overwrites[target] = discord.PermissionOverwrite(**perms)
            try:
                await channel.edit(overwrites=new_overwrites)
                restored_channels += 1
            except Exception as e:
                logger.error(f"Error restoring permissions for channel {channel.name}: {e}")
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
            "• `/sync_channels` - Wipes all overwrites, sets bot full perms, 2 roles per category (READ,WRITE), then short_lang logic.\n"
            "• `/rollback` - Restore channel permissions from the last backup.\n"
            "• `/admin_add <user>` - Add a bot admin for this server.\n"
            "• `/admin_remove <user>` - Remove a bot admin for this server.\n"
            "• `/help` - Display this help message.\n\n"
            "Only bot admins (or the server owner) can use admin commands.\n"
            "For further assistance, please refer to the documentation."
        )
        await interaction.response.send_message(help_message, ephemeral=True)

    @app_commands.command(name="admin_add", description="Add a bot admin for this server")
    async def admin_add(self, interaction: discord.Interaction, user: discord.Member):
        config = self.load_server_config(interaction.guild_id)
        if not self.is_bot_admin(interaction.user, interaction.guild, config):
            await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
            return
        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ The server owner is always an admin and cannot be added.", ephemeral=True)
            return
        admins = self.get_bot_admins(interaction.guild, config)
        if str(user.id) in admins:
            await interaction.response.send_message("ℹ️ That user is already a bot admin.", ephemeral=True)
            return
        admins.append(str(user.id))
        config["bot_admins"] = admins
        self.save_server_config(interaction.guild_id, config)
        await interaction.response.send_message(f"✅ {user.mention} has been added as a bot admin.", ephemeral=True)

    @app_commands.command(name="admin_remove", description="Remove a bot admin for this server")
    async def admin_remove(self, interaction: discord.Interaction, user: discord.Member):
        config = self.load_server_config(interaction.guild_id)
        if not self.is_bot_admin(interaction.user, interaction.guild, config):
            await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
            return
        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ The server owner cannot be removed from bot admin.", ephemeral=True)
            return
        admins = self.get_bot_admins(interaction.guild, config)
        if str(user.id) not in admins:
            await interaction.response.send_message("ℹ️ That user is not a bot admin.", ephemeral=True)
            return
        admins.remove(str(user.id))
        config["bot_admins"] = admins
        self.save_server_config(interaction.guild_id, config)
        await interaction.response.send_message(f"✅ {user.mention} has been removed from bot admin.", ephemeral=True)

    @app_commands.command(name="admin_list", description="Display the list of bot admins for this server")
    async def admin_list(self, interaction: discord.Interaction):
        config = self.load_server_config(interaction.guild_id)
        admins = self.get_bot_admins(interaction.guild, config)
        if not admins:
            await interaction.response.send_message("ℹ️ No bot admins configured for this server.", ephemeral=True)
            return

        admin_list = []
        for admin_id in admins:
            member = interaction.guild.get_member(int(admin_id))
            if member:
                admin_list.append(f"{member.mention} (`{member.id}`)")
            else:
                admin_list.append(f"<@{admin_id}> (`{admin_id}`)")
        message = "**Bot Admins for this server:**\n" + "\n".join(admin_list)
        await interaction.response.send_message(message, ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        config = self.load_server_config(after.id)
        admins = self.get_bot_admins(after, config)
        if str(after.owner_id) not in admins:
            admins.append(str(after.owner_id))
            config["bot_admins"] = admins
            self.save_server_config(after.id, config)
            logger.debug(f"Guild owner updated for {after.name}; new owner added to bot_admins.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        config = self.load_server_config(guild.id)
        admins = self.get_bot_admins(guild, config)
        if str(member.id) in admins and member.id != guild.owner_id:
            admins.remove(str(member.id))
            config["bot_admins"] = admins
            self.save_server_config(guild.id, config)
            logger.debug(f"Removed {member} from bot_admins because they left {guild.name}.")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        config_path = self.get_server_config_path(guild.id)
        if os.path.exists(config_path):
            os.remove(config_path)
            logger.info(f"Cleaned up configuration for guild {guild.name} after removal.")


async def setup(bot: commands.Bot):
    await bot.add_cog(GameConfig(bot))
