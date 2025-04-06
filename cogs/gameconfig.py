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
# 2 rôles par catégorie : READ et WRITE
# Sans view_channel pour qu’ils se cumulent avec le rôle guilde+langue
# -------------------------------------------------------------------------
READ_ONLY_PERMS = discord.PermissionOverwrite(
    # Pas de view_channel
    read_message_history=True,
    send_messages=False
)
READ_WRITE_PERMS = discord.PermissionOverwrite(
    # Pas de view_channel
    read_message_history=True,
    send_messages=True,
    attach_files=True,
    embed_links=True,
    add_reactions=True
)

# -------------------------------------------------------------------------
# Permissions basiques pour @everyone = pas de vue
# -------------------------------------------------------------------------
EVERYONE_BASIC = discord.PermissionOverwrite(
    view_channel=True,
    read_message_history=True,
    send_messages=True,
    send_tts_messages=True,
    attach_files=True,
    embed_links=True,
    add_reactions=True,
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
            # new est vide => rien à mettre
            return False
        await channel.set_permissions(target, overwrite=overwrite, reason=reason)
        return True
    else:
        if needs_update(current, overwrite):
            await channel.set_permissions(target, overwrite=overwrite, reason=reason)
            return True
    return False

async def remove_all_overwrites_except_everyone(channel: discord.abc.GuildChannel) -> None:
    """
    Retire tous les overwrites, puis remet @everyone = EVERYONE_BASIC (view_channel=False).
    """
    everyone_role = channel.guild.default_role
    await channel.edit(overwrites={})
    await channel.set_permissions(everyone_role, overwrite=EVERYONE_BASIC, reason="Wipe overwrites except @everyone")

class GameConfig(commands.Cog):
    """Configuration pour cloisonner par guilde+langue, plus 2 rôles par catégorie (READ/WRITE)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.BASE_DIR = "Guilds"
        os.makedirs(self.BASE_DIR, exist_ok=True)
        # Met à jour la config pour tous les serveurs au démarrage
        self.bot.loop.create_task(self.update_all_server_configs())

    # ===============================
    # Méthode statique pour créer le décorateur
    # ===============================
    @staticmethod
    def bot_admin_only():
        """
        Retourne un décorateur app_commands.check
        qui vérifie si l'utilisateur est admin du bot dans ce serveur.
        """
        async def predicate(interaction: discord.Interaction) -> bool:
            # On récupère la Cog GameConfig
            cog = interaction.client.get_cog("GameConfig")
            if not cog:
                return False  # si la cog n'est pas trouvée

            # Vérifie qu'on est bien dans un serveur
            if not interaction.guild_id:
                return False

            # Charge la config du serveur (fichier JSON, etc.)
            config = cog.load_server_config(interaction.guild_id)

            # Appel de la méthode is_bot_admin(...) de la cog
            return cog.is_bot_admin(interaction.user, interaction.guild, config)
        return app_commands.check(predicate)

    # ---------------------------------------------------------------------
    # Fonctions utilitaires de config serveur (fichiers JSON)
    # ---------------------------------------------------------------------
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
                logger.error(f"Erreur lors du chargement config server {server_id}: {e}")
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

    async def update_all_server_configs(self):
        """Scan et met à jour tous les fichiers de config pour ajouter les clés manquantes."""
        guilds_folder = self.BASE_DIR
        for folder in os.listdir(guilds_folder):
            config_path = os.path.join(guilds_folder, folder, "config.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception as e:
                    logger.error(f"Erreur lecture config pour guilde {folder}: {e}")
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
                        logger.info(f"Config mise à jour pour la guilde {folder}.")
                    except Exception as e:
                        logger.error(f"Erreur mise à jour config pour guilde {folder}: {e}")

    # ---------------------------------------------------------------------
    # Fonctions pour créer/trouver un rôle "bots"
    # ---------------------------------------------------------------------
    async def ensure_bots_role(self, guild: discord.Guild) -> discord.Role:
        """
        Vérifie l'existence du rôle "bots". Le crée si besoin.
        Ne lui donne pas de permissions "server" globales,
        parce qu'on utilisera des overwrites "BOT_FULL_PERMS" par canal.
        """
        role_name = "bots"
        bots_role = discord.utils.get(guild.roles, name=role_name)
        if not bots_role:
            try:
                bots_role = await guild.create_role(name=role_name)
                logger.info(f"Création du rôle {role_name} pour ce serveur (ID={guild.id})")
            except Exception as e:
                logger.error(f"Impossible de créer le rôle {role_name} : {e}")
                return None
        return bots_role

    # ---------------------------------------------------------------------
    # Sauvegarde / restauration des permissions (backup en JSON)
    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    # Autocomplétions (langues, categories, guildes)
    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    # Vérification admins du bot
    # ---------------------------------------------------------------------
    def get_bot_admins(self, guild: discord.Guild, config: dict) -> list:
        if "bot_admins" not in config or not config["bot_admins"]:
            config["bot_admins"] = [str(guild.owner_id)]
            self.save_server_config(guild.id, config)
        return config["bot_admins"]

    def is_bot_admin(self, member: discord.Member, guild: discord.Guild, config: dict) -> bool:
        admins = self.get_bot_admins(guild, config)
        return str(member.id) in admins or member.id == guild.owner_id

    # ---------------------------------------------------------------------
    # Commandes Slash
    # ---------------------------------------------------------------------

    @app_commands.command(name="full_reset_permissions", description="Efface toutes les permissions de tous les salons, sauf @everyone.")
    @bot_admin_only()
    async def full_reset_permissions(self, interaction: discord.Interaction):
        """
        Cette commande va passer sur tous les salons du serveur et 
        supprimer tous les overwrites, puis remettre @everyone = EVERYONE_BASIC.
        """
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(
                "❌ Cette commande ne peut être utilisée qu'en serveur.",
                ephemeral=True
            )
            return

        # Pour éviter les timeouts, on répond d'abord
        await interaction.response.defer(ephemeral=True)

        # On boucle sur tous les salons
        count_channels = len(guild.channels)
        modified_channels = 0

        for i, channel in enumerate(guild.channels, start=1):
            # On supprime tous les overwrites
            try:
                # On édite le salon avec un dictionnaire vide
                await channel.edit(overwrites={})
                # Ensuite, on ajoute le overwrite de @everyone
                everyone_role = guild.default_role
                await channel.set_permissions(everyone_role, overwrite=EVERYONE_BASIC)
                modified_channels += 1
            except Exception as e:
                print(f"[full_reset_permissions] Erreur sur le channel {channel.name} ({channel.id}) : {e}")

            # Petite pause pour éviter d'éventuels "rate limits"
            await asyncio.sleep(0.4)

        msg = (
            f"✅ Réinitialisation terminée pour **{modified_channels}** salons "
            f"(sur {count_channels} trouvés)."
        )
        await interaction.followup.send(msg, ephemeral=True)
    
    @app_commands.command(name="guild_add", description="Ajoute une nouvelle guilde de jeu (max 10).")
    @bot_admin_only()
    async def guild_add(self, interaction: discord.Interaction, name: str):
        """Ajoute une guilde dans la config, puis crée les rôles de langue correspondants."""
        server_id = interaction.guild_id
        guild = interaction.guild
        config = self.load_server_config(server_id)
        guildes = config.get("guildes", {})

        if len(guildes) >= 10:
            await interaction.response.send_message("⚠️ Tu as déjà 10 guildes de jeu. Limite atteinte.", ephemeral=True)
            return

        if not guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ Je n'ai pas la permission `Manage Roles`.\n"
                "Vérifie que mon rôle est plus haut et que j'ai bien cette autorisation.",
                ephemeral=True
            )
            return

        # Génère un ID unique (juste un entier incrémental)
        existing_ids = [int(g_id) for g_id in guildes.keys() if g_id.isdigit()]
        new_id = 1
        while new_id in existing_ids:
            new_id += 1

        # Génère un base_prefix
        def generate_prefix(nom: str, existing_prefixes: list) -> str:
            words = nom.split()
            initials = "".join([w[0].upper() for w in words if w])
            if len(initials) >= 3:
                prefix = initials[:3]
            else:
                prefix = initials.ljust(3, 'X')
            if prefix not in existing_prefixes:
                return prefix
            base = prefix[:2]
            for digit in range(1, 10):
                new_p = f"{base}{digit}"
                if new_p not in existing_prefixes:
                    return new_p
            return prefix + "0"

        existing_prefixes = [g.get("base_prefix") for g in guildes.values()]
        base_prefix = generate_prefix(name, existing_prefixes)

        guild_config = {
            "id": new_id,
            "name": name,
            "base_prefix": base_prefix
        }
        config["guildes"][str(new_id)] = guild_config
        self.save_server_config(server_id, config)

        # Crée les rôles guilde+langue
        for lang_code in config.get("languages", {}):
            role_name = f"Role_{base_prefix}_{lang_code}"
            existing_role = discord.utils.get(guild.roles, name=role_name)
            if existing_role is None:
                try:
                    await guild.create_role(name=role_name)
                except Exception as e:
                    logger.error(f"Erreur création du rôle {role_name}: {e}")

        await interaction.response.send_message(
            f"✅ Guilde de jeu ajoutée : ID **{new_id}**, préfixe **{base_prefix}**.",
            ephemeral=True
        )

    @app_commands.command(name="config_show", description="Affiche la configuration du serveur")
    @bot_admin_only()
    async def config_show(self, interaction: discord.Interaction):
        server_id = interaction.guild_id
        config = self.load_server_config(server_id)
        game_guilds = config.get("guildes", {})
        global_languages = config.get("languages", {})

        message = "**🛠 Configuration du serveur**\n\n"

        message += "**📚 Guildes de jeu :**\n"
        if game_guilds:
            for gg_id, gg in game_guilds.items():
                message += f"• **ID {gg_id}** | Nom: *{gg.get('name', 'N/A')}* | Préfixe: **{gg.get('base_prefix', 'N/A')}**\n"
        else:
            message += "• Aucune guilde de jeu configurée.\n"

        message += "\n**🌐 Langues configurées :**\n"
        if global_languages:
            for code, name in global_languages.items():
                message += f"• **{name}** ({code})\n"
        else:
            message += "• Aucune langue configurée.\n"

        message += "\n**🗂 Catégories allouées :**\n"
        allocations = await fetch_all_category_allocations(server_id)
        if allocations:
            for alloc in allocations:
                # (category_id, category_name, allocated_game_guild_id, allocated_game_guild)
                cat_id, cat_name, allocated_game_guild_id, allocated_game_guild = alloc
                message += f"• Catégorie: *{cat_name}* (ID: {cat_id})\n"
                message += f"  ↳ Allouée à: **{allocated_game_guild}** (ID: {allocated_game_guild_id})\n"
        else:
            message += "• Aucune catégorie allouée.\n"

        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="cat_allocate", description="Alloue une catégorie à une guilde de jeu")
    @bot_admin_only()
    @app_commands.autocomplete(cat_id=cat_name_autocomplete, guilde=guilde_autocomplete)
    @app_commands.describe(cat_id="ID de la catégorie", guilde="Nom ou préfixe de la guilde de jeu")
    async def cat_allocate(self, interaction: discord.Interaction, cat_id: str, guilde: str):
        if interaction.guild is None:
            await interaction.response.send_message("⚠️ À utiliser dans un serveur.", ephemeral=True)
            return

        guild_obj = interaction.guild
        guild_id = guild_obj.id
        category = discord.utils.get(guild_obj.categories, id=int(cat_id))
        if not category:
            await interaction.response.send_message(f"❌ Catégorie introuvable pour ID {cat_id}.", ephemeral=True)
            return

        config = self.load_server_config(guild_id)
        game_guilds = config.get("guildes", {})

        allocated_game_guild_id = None
        allocated_game_guild_prefix = None
        for gg_id, gg_config in game_guilds.items():
            bp = gg_config.get("base_prefix", "")
            nm = gg_config.get("name", "")
            if bp.lower() == guilde.lower() or nm.lower() == guilde.lower():
                allocated_game_guild_id = int(gg_id)
                allocated_game_guild_prefix = bp
                break

        if allocated_game_guild_id is None:
            await interaction.response.send_message(f"❌ Guilde de jeu '{guilde}' introuvable.", ephemeral=True)
            return

        try:
            # On stocke en DB
            await allocate_category(
                category_id=category.id,
                guild_id=guild_id,
                category_name=category.name,
                allocated_game_guild_id=allocated_game_guild_id,
                allocated_game_guild=allocated_game_guild_prefix
            )
            await interaction.response.send_message(
                f"✅ Catégorie **{category.name}** allouée à la guilde **{guilde}**.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur d'allocation : {e}", ephemeral=True)

    @app_commands.command(name="guild_list", description="Liste les guildes de jeu configurées")
    async def guild_list(self, interaction: discord.Interaction):
        server_id = interaction.guild_id
        config = self.load_server_config(server_id)
        guildes = config.get("guildes", {})

        if not guildes:
            await interaction.response.send_message("ℹ️ Aucune guilde de jeu configurée.", ephemeral=True)
            return

        message = "**Liste des guildes de jeu :**\n"
        for g_id, g_config in guildes.items():
            message += f"• ID {g_id} | Nom: **{g_config.get('name')}**, Préfixe: **{g_config.get('base_prefix')}**\n"
            if config.get("languages"):
                for lang_code in config["languages"]:
                    full_prefix = f"{g_config.get('base_prefix')}_{lang_code}"
                    message += f"   - Langue: **{lang_code}**, Rôle: **Role_{full_prefix}**\n"

        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="server_list_languages", description="Liste les langues configurées sur ce serveur")
    @bot_admin_only()
    async def server_list_languages(self, interaction: discord.Interaction):
        server_id = interaction.guild_id
        config = self.load_server_config(server_id)
        languages = config.get("languages", {})

        if not languages:
            await interaction.response.send_message("ℹ️ Aucune langue configurée.", ephemeral=True)
            return

        message = "**Langues configurées :**\n"
        for code, name in languages.items():
            message += f"• **{name}** ({code})\n"

        await interaction.response.send_message(message, ephemeral=True)

    async def ensure_read_write_roles(self, guild: discord.Guild, category: discord.CategoryChannel):
        """
        Vérifie l'existence de <NomCat>_READ et <NomCat>_WRITE, les crée au besoin.
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

    @app_commands.command(name="sync_channels", description="Réinitialise puis applique les permissions par guilde+langue, plus roles READ/WRITE.")
    @bot_admin_only()
    async def sync_channels(self, interaction: discord.Interaction):
        logger.debug("===== [sync_channels] Début =====")
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Impossible de synchroniser hors d'un serveur.", ephemeral=True)
            return

        bots_role = await self.ensure_bots_role(guild)
        if not bots_role:
            await interaction.followup.send("❌ Échec : impossible de créer/trouver le rôle 'bots'.", ephemeral=True)
            return

        server_id = guild.id
        config = self.load_server_config(server_id)
        game_guilds = config.get("guildes", {})
        global_langs = config.get("languages", {})

        # Sauvegarde initiale
        backup_data = self.backup_channel_permissions(guild)
        self.save_backup(server_id, backup_data)

        set_permissions_count = 0
        processed_count = 0

        # Prépare un dict { base_prefix: { lang_code: role } }
        # ex: { "G1": {"EN": <Role 123>, "FR": <Role 456>}, "G2": {...} }
        roles_dict = {}
        for gg_conf in game_guilds.values():
            bp = gg_conf.get("base_prefix")
            if not bp:
                continue
            local_map = {}
            for lang_code in global_langs.keys():
                role_name = f"Role_{bp}_{lang_code}"
                role_obj = discord.utils.get(guild.roles, name=role_name)
                if not role_obj:
                    # On crée si manquant
                    try:
                        role_obj = await guild.create_role(name=role_name)
                        logger.debug(f"Créé le rôle {role_name}")
                    except Exception as e:
                        logger.error(f"Erreur création du rôle {role_name}: {e}")
                        continue
                local_map[lang_code.upper()] = role_obj
            roles_dict[bp] = local_map

        async def maybe_sleep():
            await asyncio.sleep(PERMISSION_SET_DELAY)

        # Parcours de tous les canaux
        channels_list = guild.channels
        logger.debug(f"[sync_channels] {len(channels_list)} canaux trouvés.")
        for idx, channel in enumerate(channels_list, start=1):
            logger.debug(f"[{idx}/{len(channels_list)}] Traitement du canal: {channel.name} (ID={channel.id})")

            # Wipe complet : on enlève tout, on met @everyone = false
            await remove_all_overwrites_except_everyone(channel)
            set_permissions_count += 1
            await maybe_sleep()

            # Bot full perms
            changed = await set_perms_if_needed(channel, bots_role, BOT_FULL_PERMS, reason="bots role full perms")
            if changed:
                set_permissions_count += 1
                await maybe_sleep()

            # Si c'est une catégorie, on gère les rôles <cat>_READ / <cat>_WRITE
            if isinstance(channel, discord.CategoryChannel):
                read_role, write_role = await self.ensure_read_write_roles(guild, channel)
                c1 = await set_perms_if_needed(channel, read_role, READ_ONLY_PERMS, reason="Cat read role")
                if c1: set_permissions_count += 1; await maybe_sleep()
                c2 = await set_perms_if_needed(channel, write_role, READ_WRITE_PERMS, reason="Cat write role")
                if c2: set_permissions_count += 1; await maybe_sleep()

                # Quelle guilde est allouée ?
                cat_alloc = await fetch_category_allocation(channel.id, guild.id)
                if cat_alloc:
                    # cat_alloc => (allocated_game_guild_id, allocated_game_guild)
                    allocated_game_guild_id, allocated_game_guild_prefix = cat_alloc[2], cat_alloc[3]
                    if allocated_game_guild_prefix in roles_dict:
                        # On autorise seulement cette guilde à voir
                        for lang_code, role_obj in roles_dict[allocated_game_guild_prefix].items():
                            ow = discord.PermissionOverwrite(view_channel=True)
                            changed = await set_perms_if_needed(channel, role_obj, ow, reason="Cat allocated to 1 guild")
                            if changed:
                                set_permissions_count += 1
                                await maybe_sleep()
                else:
                    # Pas allouée => c'est commun => union de toutes les guildes
                    for bp_map in roles_dict.values():
                        for role_obj in bp_map.values():
                            ow = discord.PermissionOverwrite(view_channel=True)
                            changed = await set_perms_if_needed(channel, role_obj, ow, reason="Cat public")
                            if changed:
                                set_permissions_count += 1
                                await maybe_sleep()

            else:
                # Channel texte ou vocal
                # On vérifie s'il est connu dans la DB "TextChannel"
                known = await check_text_channel(channel.id)
                short_lang = None

                if known:
                    ch_data = await fetch_text_channel(channel.id)
                    # On suppose short_language en position 7
                    # (id=0, jump_url=1, mention=2, name=3, type=4, guild_id=5, Webhook_id=6, short_language=7, etc.)
                    if ch_data and len(ch_data) > 7 and ch_data[7]:
                        short_lang = str(ch_data[7]).upper()

                # On regarde la catégorie parente
                cat_alloc = None
                if channel.category:
                    cat_alloc = await fetch_category_allocation(channel.category.id, guild.id)

                if cat_alloc:
                    # cat_alloc => (category_id, guild_id, allocated_game_guild_id, allocated_game_guild)
                    allocated_game_guild_prefix = cat_alloc[3]  # ex: "G1"
                    # => seuls les rôles de cette guilde
                    if allocated_game_guild_prefix in roles_dict:
                        map_guild_roles = roles_dict[allocated_game_guild_prefix]
                        if short_lang:
                            # Seule la langue short_lang => True, les autres => False
                            for lc, role_obj in map_guild_roles.items():
                                if lc == short_lang:
                                    ow = discord.PermissionOverwrite(view_channel=True)
                                else:
                                    ow = discord.PermissionOverwrite(view_channel=False)
                                changed = await set_perms_if_needed(channel, role_obj, ow, reason="Guild cat + short_lang")
                                if changed:
                                    set_permissions_count += 1
                                    await maybe_sleep()
                        else:
                            # Pas de langue => tous les rôles de la guilde => True
                            for role_obj in map_guild_roles.values():
                                ow = discord.PermissionOverwrite(view_channel=True)
                                changed = await set_perms_if_needed(channel, role_obj, ow, reason="Guild cat no lang")
                                if changed:
                                    set_permissions_count += 1
                                    await maybe_sleep()
                else:
                    # Catégorie pas allouée => c'est public => union de toutes les guildes
                    if short_lang:
                        # Seule cette langue => True, les autres => False, dans TOUTES les guildes
                        for bp_map in roles_dict.values():
                            for lc, role_obj in bp_map.items():
                                if lc == short_lang:
                                    ow = discord.PermissionOverwrite(view_channel=True)
                                else:
                                    ow = discord.PermissionOverwrite(view_channel=False)
                                changed = await set_perms_if_needed(channel, role_obj, ow, reason="Public cat + short_lang")
                                if changed:
                                    set_permissions_count += 1
                                    await maybe_sleep()
                    else:
                        # Aucune langue => tous => True
                        for bp_map in roles_dict.values():
                            for role_obj in bp_map.values():
                                ow = discord.PermissionOverwrite(view_channel=True)
                                changed = await set_perms_if_needed(channel, role_obj, ow, reason="Public cat no lang")
                                if changed:
                                    set_permissions_count += 1
                                    await maybe_sleep()

            processed_count += 1
            logger.debug(f"[{idx}/{len(channels_list)}] Fin canal '{channel.name}'.")

        msg = f"✅ Permissions synchronisées pour **{processed_count}** canaux (set_permissions appelé {set_permissions_count} fois)."
        await interaction.followup.send(msg, ephemeral=True)
        logger.debug("===== [sync_channels] Fin =====")

    @app_commands.command(name="rollback", description="Restaure les permissions depuis le dernier backup")
    @bot_admin_only()
    async def rollback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        server_id = interaction.guild_id
        guild = interaction.guild
        backup_data = self.load_backup(server_id)
        if not backup_data:
            await interaction.followup.send("ℹ️ Aucun backup trouvé.", ephemeral=True)
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
                logger.error(f"Erreur restauration perms pour {channel.name}: {e}")

        await interaction.followup.send(f"✅ {restored_channels} canaux restaurés.", ephemeral=True)

    @app_commands.command(name="help", description="Aide détaillée pour les commandes du bot")
    @bot_admin_only()
    async def help(self, interaction: discord.Interaction):
        help_message = (
            "**Aide du bot**\n\n"
            "**Commandes générales :**\n"
            "• `/guild_add <name>` - Ajoute une nouvelle guilde de jeu.\n"
            "• `/config_show` - Affiche la configuration du serveur.\n"
            "• `/cat_allocate <cat_id> <guilde>` - Alloue une catégorie à une guilde.\n"
            "• `/guild_list` - Liste les guildes de jeu.\n"
            "• `/server_list_languages` - Liste les langues configurées.\n"
            "• `/sync_channels` - Réinitialise les overwrites et applique la logique guilde+langue.\n"
            "• `/rollback` - Restaure les permissions depuis le dernier backup.\n"
            "• `/admin_add <user>` - Ajoute un administrateur du bot.\n"
            "• `/admin_remove <user>` - Retire un administrateur du bot.\n"
            "• `/admin_list` - Liste les administrateurs du bot.\n"
            "• `/help` - Affiche ce message d'aide.\n\n"
            "Seuls les administrateurs du bot (ou le owner du serveur) peuvent exécuter certaines commandes.\n"
        )
        await interaction.response.send_message(help_message, ephemeral=True)

    @app_commands.command(name="admin_add", description="Ajoute un administrateur du bot")
    @bot_admin_only()
    async def admin_add(self, interaction: discord.Interaction, user: discord.Member):
        config = self.load_server_config(interaction.guild_id)
        if not self.is_bot_admin(interaction.user, interaction.guild, config):
            await interaction.response.send_message("❌ Vous n'êtes pas autorisé à faire ça.", ephemeral=True)
            return
        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ Le propriétaire du serveur est déjà admin.", ephemeral=True)
            return
        admins = self.get_bot_admins(interaction.guild, config)
        if str(user.id) in admins:
            await interaction.response.send_message("ℹ️ Cet utilisateur est déjà admin du bot.", ephemeral=True)
            return
        admins.append(str(user.id))
        config["bot_admins"] = admins
        self.save_server_config(interaction.guild_id, config)
        await interaction.response.send_message(f"✅ {user.mention} est maintenant admin du bot.", ephemeral=True)

    @app_commands.command(name="admin_remove", description="Retire un administrateur du bot")
    @bot_admin_only()
    async def admin_remove(self, interaction: discord.Interaction, user: discord.Member):
        config = self.load_server_config(interaction.guild_id)
        if not self.is_bot_admin(interaction.user, interaction.guild, config):
            await interaction.response.send_message("❌ Vous n'êtes pas autorisé à faire ça.", ephemeral=True)
            return
        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ Le propriétaire du serveur ne peut pas être retiré.", ephemeral=True)
            return
        admins = self.get_bot_admins(interaction.guild, config)
        if str(user.id) not in admins:
            await interaction.response.send_message("ℹ️ Cet utilisateur n'est pas admin du bot.", ephemeral=True)
            return
        admins.remove(str(user.id))
        config["bot_admins"] = admins
        self.save_server_config(interaction.guild_id, config)
        await interaction.response.send_message(f"✅ {user.mention} n'est plus admin du bot.", ephemeral=True)

    @app_commands.command(name="admin_list", description="Liste les administrateurs du bot")
    @bot_admin_only()
    async def admin_list(self, interaction: discord.Interaction):
        config = self.load_server_config(interaction.guild_id)
        admins = self.get_bot_admins(interaction.guild, config)
        if not admins:
            await interaction.response.send_message("ℹ️ Aucun admin configuré.", ephemeral=True)
            return

        admin_list = []
        for admin_id in admins:
            member = interaction.guild.get_member(int(admin_id))
            if member:
                admin_list.append(f"{member.mention} (`{member.id}`)")
            else:
                admin_list.append(f"<@{admin_id}> (`{admin_id}`)")

        message = "**Admins du bot :**\n" + "\n".join(admin_list)
        await interaction.response.send_message(message, ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Si le propriétaire du serveur change, on s'assure qu'il est admin du bot."""
        config = self.load_server_config(after.id)
        admins = self.get_bot_admins(after, config)
        if str(after.owner_id) not in admins:
            admins.append(str(after.owner_id))
            config["bot_admins"] = admins
            self.save_server_config(after.id, config)
            logger.debug(f"Nouveau propriétaire pour {after.name}, ajouté à bot_admins.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Si un admin du bot quitte le serveur, on le retire de la liste."""
        guild = member.guild
        config = self.load_server_config(guild.id)
        admins = self.get_bot_admins(guild, config)
        if str(member.id) in admins and member.id != guild.owner_id:
            admins.remove(str(member.id))
            config["bot_admins"] = admins
            self.save_server_config(guild.id, config)
            logger.debug(f"Retiré {member} des bot_admins car il a quitté {guild.name}.")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        # Nettoyage du fichier config quand le bot quitte un serveur
        config_path = self.get_server_config_path(guild.id)
        if os.path.exists(config_path):
            os.remove(config_path)
            logger.info(f"Nettoyage de la config pour la guilde {guild.name} (ID {guild.id}).")

async def setup(bot: commands.Bot):
    await bot.add_cog(GameConfig(bot))
