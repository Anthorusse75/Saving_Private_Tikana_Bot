import discord
from discord.ext import commands
from discord import app_commands
import os, json, asyncio
import googletrans

from config import TOKEN
from Func_SQL.funcSQL_utils import fetch_text_channel, check_text_channel
from Func_SQL.funcSQL_categories import allocate_category, fetch_category_allocation, fetch_all_category_allocations

# ───────────────────────────────────────────────────────────────
# Répertoire de base pour la configuration des serveurs
# ───────────────────────────────────────────────────────────────
BASE_DIR = "Guilds"
if not os.path.exists(BASE_DIR):
    os.mkdir(BASE_DIR)

# ───────────────────────────────────────────────────────────────
# Fonctions de gestion de la configuration serveur
# ───────────────────────────────────────────────────────────────
def get_server_folder(server_id: int) -> str:
    folder = os.path.join(BASE_DIR, str(server_id))
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder

def get_server_config_path(server_id: int) -> str:
    return os.path.join(get_server_folder(server_id), "config.json")

def load_server_config(server_id: int) -> dict:
    path = get_server_config_path(server_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Erreur lors du chargement de la config pour le serveur {server_id} : {e}")
            config = {}
    else:
        config = {}
    if "guildes" not in config:
        config["guildes"] = {}
    if "languages" not in config:
        config["languages"] = {}
    return config

def save_server_config(server_id: int, config: dict):
    path = get_server_config_path(server_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def generate_prefix(name: str, existing_prefixes: list) -> str:
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

# ───────────────────────────────────────────────────────────────
# Fonctions de backup/rollback des permissions des salons
# ───────────────────────────────────────────────────────────────
def backup_channel_permissions(guild: discord.Guild) -> dict:
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
                "permissions": overwrite._values  # Note: _values est interne, à utiliser avec précaution.
            }
        backup[str(channel.id)] = overwrites_data
    return backup

def save_backup(server_id: int, backup_data: dict):
    path = os.path.join(get_server_folder(server_id), "permissions_backup.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=4)

def load_backup(server_id: int) -> dict:
    path = os.path.join(get_server_folder(server_id), "permissions_backup.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# ───────────────────────────────────────────────────────────────
# Autocomplétion pour les langues via googletrans
# ───────────────────────────────────────────────────────────────
async def language_autocomplete(interaction: discord.Interaction, current: str):
    choices = []
    for code, name in googletrans.LANGUAGES.items():
        if current.lower() in code.lower() or current.lower() in name.lower():
            choices.append(app_commands.Choice(name=f"{name.title()} ({code.upper()})", value=code.upper()))
    return choices[:25]

# ───────────────────────────────────────────────────────────────
# Autocomplétion pour le nom de catégorie et la guilde de jeu
# ───────────────────────────────────────────────────────────────
async def cat_name_autocomplete(interaction: discord.Interaction, current: str):
    choices = []
    if interaction.guild:
        for cat in interaction.guild.categories:
            display_name = f"{cat.name} (ID: {cat.id})"
            if current.lower() in cat.name.lower():
                choices.append(app_commands.Choice(name=display_name, value=str(cat.id)))
    return choices[:25]

async def guilde_autocomplete(interaction: discord.Interaction, current: str):
    choices = []
    config = load_server_config(interaction.guild_id)
    game_guilds = config.get("guildes", {})
    for gg_id, gg in game_guilds.items():
        base_prefix = gg.get("base_prefix", "")
        name = gg.get("name", "")
        if current.lower() in base_prefix.lower() or current.lower() in name.lower():
            display = f"{name} ({base_prefix})"
            choices.append(app_commands.Choice(name=display, value=base_prefix))
    return choices[:25]

# ───────────────────────────────────────────────────────────────
# Initialisation du bot avec les intents nécessaires
# ───────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ───────────────────────────────────────────────────────────────
# Commande /guild_add
# ───────────────────────────────────────────────────────────────
@bot.tree.command(name="guild_add", description="Ajouter une nouvelle guilde de jeu (max 10 par serveur)")
async def guild_add(interaction: discord.Interaction, name: str):
    server_id = interaction.guild_id
    guild = interaction.channel.guild
    config = load_server_config(server_id)
    guildes = config.get("guildes", {})

    if len(guildes) >= 10:
        await interaction.response.send_message("⚠️ Nombre maximum de guildes de jeu atteint (10).", ephemeral=True)
        return

    if not guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "❌ Je n'ai pas la permission de **créer des rôles**.\n"
            "👉 Vérifiez que j'ai la permission `Gérer les rôles` et que mon rôle est placé au-dessus des rôles à créer.\n"
            "⚙️ Pour régler cela, allez dans Paramètres du serveur > Rôles et déplacez mon rôle vers le haut.",
            ephemeral=True
        )
        return

    existing_prefixes = [g.get("base_prefix") for g in guildes.values()]
    base_prefix = generate_prefix(name, existing_prefixes)

    new_id = 1
    existing_ids = [int(g_id) for g_id in guildes.keys() if g_id.isdigit()]
    while new_id in existing_ids:
        new_id += 1

    guild_config = {"id": new_id, "name": name, "base_prefix": base_prefix}
    config["guildes"][str(new_id)] = guild_config
    save_server_config(server_id, config)

    # Création automatique des rôles pour chaque langue déjà définie globalement
    for lang_code in config.get("languages", {}):
        full_prefix = f"{base_prefix}_{lang_code}"
        role_name = f"Role_{full_prefix}"
        existing_role = discord.utils.get(guild.roles, name=role_name)
        if existing_role is None:
            try:
                await guild.create_role(name=role_name)
            except Exception as e:
                print(f"Erreur lors de la création du rôle {role_name} : {e}")

    await interaction.response.send_message(
        f"✅ Guilde de jeu ajoutée avec ID **{new_id}** et préfixe de base **{base_prefix}**.",
        ephemeral=True
    )

# ───────────────────────────────────────────────────────────────
# Commande /config_show
# ───────────────────────────────────────────────────────────────
@bot.tree.command(name="config_show", description="Afficher la configuration actuelle du serveur")
async def config_show(interaction: discord.Interaction):
    server_id = interaction.guild_id
    config = load_server_config(server_id)
    game_guilds = config.get("guildes", {})
    global_languages = config.get("languages", {})

    message = "**🛠 Configuration du serveur**\n\n"
    message += "**📚 Guildes de jeu:**\n"
    if game_guilds:
        for gg_id, gg in game_guilds.items():
            message += f"• **ID {gg_id}** | Nom : *{gg.get('name', 'N/A')}* | Préfixe : **{gg.get('base_prefix', 'N/A')}**\n"
    else:
        message += "• Aucune guilde de jeu configurée.\n"
    
    message += "\n**🌐 Langues configurées:**\n"
    if global_languages:
        for code, name in global_languages.items():
            message += f"• **{name}** ({code})\n"
    else:
        message += "• Aucune langue configurée.\n"
    
    message += "\n**🗂 Catégories allouées:**\n"
    allocations = await fetch_all_category_allocations(server_id)
    if allocations:
        for alloc in allocations:
            category_id, category_name, allocated_game_guild_id, allocated_game_guild = alloc
            message += f"• **Catégorie**: *{category_name}* (ID: `{category_id}`)\n"
            message += f"  ↳ Allouée à : **{allocated_game_guild}** (ID: `{allocated_game_guild_id}`)\n"
    else:
        message += "• Aucune catégorie allouée.\n"
    
    await interaction.response.send_message(message, ephemeral=True)

# ───────────────────────────────────────────────────────────────
# Commande /cat_allocate
# ───────────────────────────────────────────────────────────────
@bot.tree.command(name="cat_allocate", description="Allouer une catégorie à une guilde de jeu")
@app_commands.autocomplete(cat_id=cat_name_autocomplete, guilde=guilde_autocomplete)
@app_commands.describe(cat_id="ID de la catégorie", guilde="Base_prefix ou nom de la guilde de jeu")
async def cat_allocate(interaction: discord.Interaction, cat_id: str, guilde: str):
    if interaction.guild is None:
        await interaction.response.send_message("⚠️ Cette commande ne peut être utilisée que dans un serveur.", ephemeral=True)
        return
    guild_obj = interaction.guild
    guild_id = guild_obj.id

    category = None
    for cat in guild_obj.categories:
        if str(cat.id) == cat_id:
            category = cat
            break
    if category is None:
        await interaction.response.send_message(f"❌ Catégorie d'ID {cat_id} introuvable.", ephemeral=True)
        return

    config = load_server_config(guild_id)
    game_guilds = config.get("guildes", {})
    allocated_game_guild_id = None
    allocated_game_guild = None
    for gg_id, gg_config in game_guilds.items():
        if gg_config.get("base_prefix", "").lower() == guilde.lower() or gg_config.get("name", "").lower() == guilde.lower():
            allocated_game_guild_id = int(gg_id)
            allocated_game_guild = gg_config
            break
    if allocated_game_guild_id is None:
        await interaction.response.send_message(f"❌ Guilde de jeu '{guilde}' introuvable.", ephemeral=True)
        return

    try:
        await allocate_category(category.id, guild_id, category.name, allocated_game_guild_id, allocated_game_guild.get("base_prefix", ""))
        await interaction.response.send_message(
            f"✅ La catégorie **{category.name}** a été allouée à la guilde de jeu **{allocated_game_guild.get('name', guilde)}**.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de l'allocation : {e}", ephemeral=True)

# ───────────────────────────────────────────────────────────────
# Commande /guild_list
# ───────────────────────────────────────────────────────────────
@bot.tree.command(name="guild_list", description="Afficher la liste des guildes de jeu configurées sur ce serveur")
async def guild_list(interaction: discord.Interaction):
    server_id = interaction.guild_id
    guild = interaction.channel.guild
    config = load_server_config(server_id)
    guildes = config.get("guildes", {})

    if not guildes:
        await interaction.response.send_message("ℹ️ Aucune guilde de jeu configurée sur ce serveur.", ephemeral=True)
        return

    message = "Liste des guildes de jeu :\n"
    for g_id, g_config in guildes.items():
        message += f"• **ID {g_id}** - Nom : **{g_config.get('name')}**, Préfixe de base : **{g_config.get('base_prefix')}**\n"
        if config.get("languages"):
            for lang_code in config["languages"]:
                base_prefix = g_config.get("base_prefix")
                full_prefix = f"{base_prefix}_{lang_code}"
                message += f"   - Langue : **{lang_code}**, Préfixe complet : **{full_prefix}**\n"
    await interaction.response.send_message(message, ephemeral=True)

# ───────────────────────────────────────────────────────────────
# Commande /server_list_languages
# ───────────────────────────────────────────────────────────────
@bot.tree.command(name="server_list_languages", description="Afficher les langues configurées pour le serveur")
async def server_list_languages(interaction: discord.Interaction):
    server_id = interaction.guild_id
    config = load_server_config(server_id)
    languages = config.get("languages", {})
    if not languages:
        await interaction.response.send_message("ℹ️ Aucune langue n'est configurée pour ce serveur.", ephemeral=True)
        return
    message = "Langues configurées sur ce serveur :\n"
    for code, name in languages.items():
        message += f"• **{name} ({code})**\n"
    await interaction.response.send_message(message, ephemeral=True)

# ───────────────────────────────────────────────────────────────
# Commande /sync_channels
# ───────────────────────────────────────────────────────────────
@bot.tree.command(name="sync_channels", description="Synchroniser les permissions en se basant sur la DB, les allocations et la config langues")
async def sync_channels(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    server_id = interaction.guild_id
    guild_obj = interaction.channel.guild
    config = load_server_config(server_id)
    game_guilds = config.get("guildes", {})
    global_languages = config.get("languages", {})

    # Étape 0 : Backup des permissions
    backup_data = backup_channel_permissions(guild_obj)
    save_backup(server_id, backup_data)
    print("Backup effectué :", backup_data)

    # Étape 1 : Mise à jour des langues depuis la DB
    for channel in guild_obj.channels:
        exists = await check_text_channel(channel.id)
        if exists:
            ch_data = await fetch_text_channel(channel.id)
            short_lang = ch_data[7]  # Index à vérifier selon votre DB
            if short_lang:
                lang_code = short_lang.upper()
                if lang_code not in global_languages:
                    lang_full = googletrans.LANGUAGES.get(lang_code.lower(), lang_code).title()
                    global_languages[lang_code] = lang_full
    config["languages"] = global_languages
    save_server_config(server_id, config)

    # Étape 2 : Construction du mapping des rôles pour chaque guilde
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
                print(f"Rôle non trouvé : {role_name}")
        roles_dict[base_prefix] = lang_roles

    restored_count = 0

    # Étape 3 : Application de la configuration sur chaque salon/catégorie
    for channel in guild_obj.channels:
        channel_name = channel.name.lower()
        # Cas des catégories
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
                print(f"Catégorie {channel.name} configurée.")
            except Exception as e:
                print(f"Erreur configuration catégorie {channel.name}: {e}")
        # Cas des salons classiques
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
                                print(f"Channel {channel.name} configuré avec préfixe complet pour langue {short_lang}.")
                            except Exception as e:
                                print(f"Erreur configuration channel {channel.name} (préfixe complet): {e}")
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
                                print(f"Channel {channel.name} configuré via catégorie allouée pour langue {short_lang}.")
                            except Exception as e:
                                print(f"Erreur configuration channel {channel.name} via catégorie allouée: {e}")
                    if not applied:
                        # Déterminer la guilde de jeu qui possède la langue configurée
                        matching_guild = None
                        for base_prefix, lang_roles in roles_dict.items():
                            # Si cette guilde possède un rôle pour la langue du salon
                            if short_lang in lang_roles:
                                matching_guild = base_prefix
                                break
                        if matching_guild:
                            try:
                                await channel.set_permissions(guild_obj.default_role,
                                                            overwrite=discord.PermissionOverwrite(view_channel=False))
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
                                print(f"Channel {channel.name} fallback général configuré pour langue {short_lang} (matching guild: {matching_guild}).")
                            except Exception as e:
                                print(f"Erreur fallback général pour channel {channel.name}: {e}")
                        else:
                            print(f"Aucune guilde trouvée pour la langue {short_lang} dans le fallback du channel {channel.name}.")
            else:
                print(f"Channel {channel.name} non configuré en DB, ignoré.")

    await interaction.followup.send(f"✅ Permissions synchronisées pour **{restored_count}** salons.", ephemeral=True)

# ───────────────────────────────────────────────────────────────
# Commande /rollback
# ───────────────────────────────────────────────────────────────
@bot.tree.command(name="rollback", description="Restaurer l'état des permissions des salons depuis le dernier backup")
async def rollback(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    server_id = interaction.guild_id
    guild = interaction.channel.guild
    backup_data = load_backup(server_id)
    if not backup_data:
        await interaction.followup.send("ℹ️ Aucun backup n'a été trouvé.", ephemeral=True)
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
            print(f"Erreur lors de la restauration des permissions pour le salon {channel.name}: {e}")
    await interaction.followup.send(f"✅ **{restored_channels}** salons restaurés avec succès.", ephemeral=True)

# ───────────────────────────────────────────────────────────────
# Démarrage du bot
# ───────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Connecté en tant que {bot.user}.")

bot.run(TOKEN)
