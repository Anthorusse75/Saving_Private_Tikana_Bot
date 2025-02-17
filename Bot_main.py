import discord
from discord.ext import commands
from discord import app_commands
import os, json, asyncio
import googletrans

from config import TOKEN
from Func_SQL.funcSQL_utils import fetch_text_channel, check_text_channel

# --- Répertoire de base pour la configuration des serveurs ---
BASE_DIR = "Guilds"
if not os.path.exists(BASE_DIR):
    os.mkdir(BASE_DIR)

# --- Fonctions de gestion de la configuration serveur ---

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

# --- Fonctions de backup/rollback des permissions des salons ---

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
                "permissions": overwrite._values  # Utilise l'attribut _values qui est un dict
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

# --- Autocomplétion pour les langues via googletrans ---

async def language_autocomplete(interaction: discord.Interaction, current: str):
    choices = []
    for code, name in googletrans.LANGUAGES.items():
        if current.lower() in code.lower() or current.lower() in name.lower():
            choices.append(app_commands.Choice(name=f"{name.title()} ({code.upper()})", value=code.upper()))
    return choices[:25]

# --- Initialisation du bot ---
# Activation des intents avec l'intent members
intents = discord.Intents.default()
intents.members = True  # IMPORTANT : active l'accès aux membres
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Commande /guild_add ---
@bot.tree.command(name="guild_add", description="Ajouter une nouvelle guilde de jeu (max 10 par serveur)")
async def guild_add(interaction: discord.Interaction, name: str):
    server_id = interaction.guild_id
    guild = interaction.channel.guild
    config = load_server_config(server_id)
    guildes = config.get("guildes", {})

    if len(guildes) >= 10:
        await interaction.response.send_message("⚠️ Nombre maximum de guildes de jeu atteint (10).", ephemeral=True)
        return

    # Vérification de la permission de créer des rôles
    if not guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "❌ Je n'ai pas la permission de **créer des rôles**.\n"
            "👉 Veuillez vérifier que j'ai la permission `Gérer les rôles` et que mon rôle est positionné **au-dessus** des rôles à créer.\n"
            "⚙️ *Pour régler cela, allez dans Paramètres du serveur > Rôles, et déplacez mon rôle vers le haut.*",
            ephemeral=True
        )
        return

    existing_prefixes = [g.get("base_prefix") for g in guildes.values()]
    base_prefix = generate_prefix(name, existing_prefixes)

    new_id = 1
    existing_ids = [int(g_id) for g_id in guildes.keys() if g_id.isdigit()]
    while new_id in existing_ids:
        new_id += 1

    guild_config = {
        "id": new_id,
        "name": name,
        "base_prefix": base_prefix
    }
    config["guildes"][str(new_id)] = guild_config
    save_server_config(server_id, config)

    # Création automatique des rôles pour chaque langue déjà définie globalement
    for lang_code in config.get("languages", {}):
        full_prefix = base_prefix + lang_code
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

# --- Commande /guild_list ---
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
                full_prefix = g_config.get("base_prefix") + lang_code
                message += f"   - Langue : **{lang_code}**, Préfixe complet : **{full_prefix}**\n"
    await interaction.response.send_message(message, ephemeral=True)

# --- Commande /server_add_language ---
@bot.tree.command(name="server_add_language", description="Ajouter une langue au serveur (affecte toutes les guildes de jeu)")
@app_commands.autocomplete(language=language_autocomplete)
async def server_add_language(interaction: discord.Interaction, language: str):
    if language.lower() not in googletrans.LANGUAGES:
        await interaction.response.send_message("⚠️ Langue non supportée.", ephemeral=True)
        return

    server_id = interaction.guild_id
    guild = interaction.channel.guild

    # Récupérer le membre du bot dans le serveur
    bot_member = guild.me
    if bot_member is None:
        try:
            bot_member = await guild.fetch_member(bot.user.id)
        except Exception as e:
            await interaction.response.send_message(
                "❌ Impossible de récupérer mes informations de membre dans ce serveur.\n"
                "👉 Assure-toi que l'intent `members` est activé pour mon bot.",
                ephemeral=True
            )
            return

    # Vérification de la permission de créer des rôles
    if not bot_member.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "❌ Je n'ai pas la permission de **créer des rôles**.\n"
            "👉 Veuillez vérifier que j'ai la permission `Gérer les rôles` et que mon rôle est positionné **au-dessus** des rôles à créer.\n"
            "⚙️ Pour régler cela, allez dans Paramètres du serveur > Rôles et déplacez mon rôle vers le haut.",
            ephemeral=True
        )
        return

    # Suite de la commande...
    config = load_server_config(server_id)
    languages = config.get("languages", {})

    if language.upper() in languages:
        await interaction.response.send_message("⚠️ Cette langue est déjà ajoutée au serveur.", ephemeral=True)
        return

    languages[language.upper()] = googletrans.LANGUAGES[language.lower()].title()
    config["languages"] = languages
    save_server_config(server_id, config)

    # Création des rôles associés pour chaque guilde de jeu existante
    for g_config in config.get("guildes", {}).values():
        base_prefix = g_config.get("base_prefix")
        full_prefix = base_prefix + language.upper()
        role_name = f"Role_{full_prefix}"
        existing_role = discord.utils.get(guild.roles, name=role_name)
        if existing_role is None:
            try:
                await guild.create_role(name=role_name)
            except Exception as e:
                print(f"Erreur lors de la création du rôle {role_name} : {e}")

    await interaction.response.send_message(
        f"✅ Langue **{googletrans.LANGUAGES[language.lower()].title()} ({language.upper()})** ajoutée au serveur.",
        ephemeral=True
    )

# --- Commande /server_list_languages ---
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

@bot.tree.command(name="sync_channels", description="Synchroniser les permissions en se basant sur la DB et compléter la config langues")
async def sync_channels(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    server_id = interaction.guild_id
    guild_obj = interaction.channel.guild
    config = load_server_config(server_id)
    game_guilds = config.get("guildes", {})        # Ex: {"1": {"id": 1, "name": "Guilde1", "base_prefix": "GU1"}, ...}
    global_languages = config.get("languages", {})  # Langues configurées sur le serveur

    # Étape 0 : Backup de toutes les permissions avant toute modification
    backup_data = backup_channel_permissions(guild_obj)
    save_backup(server_id, backup_data)
    print("Backup effectué :", backup_data)  # Pour debug
    
    # --- Étape 1 : Mise à jour automatique des langues depuis la DB ---
    for channel in guild_obj.channels:
        exists = await check_text_channel(channel.id)
        if exists:
            ch_data = await fetch_text_channel(channel.id)
            # On suppose ici que le champ "short_language" se trouve à l'index 7
            short_lang = ch_data[7]
            if short_lang:
                lang_code = short_lang.upper()
                if lang_code not in global_languages:
                    lang_full = googletrans.LANGUAGES.get(lang_code.lower(), lang_code).title()
                    global_languages[lang_code] = lang_full
    config["languages"] = global_languages
    save_server_config(server_id, config)

    # --- Étape 2 : Construction du mapping des rôles pour chaque guilde ---
    # Pour chaque guilde de jeu, on crée un dictionnaire associant chaque code langue à son rôle.
    # Exemple : { "GU1": { "FR": role, "EN": role, "DE": role }, ... }
    roles_dict = {}
    for g_config in game_guilds.values():
        base_prefix = g_config.get("base_prefix")
        lang_roles = {}
        for lang_code in global_languages:
            full_prefix = base_prefix + lang_code
            role_name = f"Role_{full_prefix}"
            role = discord.utils.get(guild_obj.roles, name=role_name)
            if role:
                lang_roles[lang_code] = role
            else:
                print(f"Rôle non trouvé : {role_name}")
        roles_dict[base_prefix] = lang_roles
    print("Mapping des rôles :", roles_dict)

    restored_count = 0

    # --- Étape 3 : Application de la configuration sur chaque salon ---
    for channel in guild_obj.channels:
        channel_name = channel.name.lower()

        # Cas A : Le salon est une catégorie
        if isinstance(channel, discord.CategoryChannel):
            for base_prefix, lang_roles in roles_dict.items():
                if channel_name.startswith(base_prefix.lower()) or channel_name.endswith(base_prefix.lower()):
                    try:
                        await channel.set_permissions(guild_obj.default_role,
                                                      overwrite=discord.PermissionOverwrite(view_channel=False))
                        for role in lang_roles.values():
                            await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=True))
                        # Pour les autres rôles non gérés, on supprime l'overwrite explicite
                        if channel.overwrites:
                            for target, overw in channel.overwrites.items():
                                if isinstance(target, discord.Role) and target not in lang_roles.values() and target != guild_obj.default_role:
                                    new_overwrite = overw
                                    new_overwrite.view_channel = None
                                    await channel.set_permissions(target, overwrite=new_overwrite)
                        restored_count += 1
                        print(f"Catégorie {channel.name} configurée pour la guilde {base_prefix}")
                    except Exception as e:
                        print(f"Erreur dans la configuration de la catégorie {channel.name}: {e}")
                    break  # Une catégorie correspond à une seule guilde

        # Cas B : Salon classique (texte, vocal, etc.)
        else:
            exists = await check_text_channel(channel.id)
            if exists:
                ch_data = await fetch_text_channel(channel.id)
                short_lang = ch_data[7]
                if short_lang:
                    short_lang = short_lang.upper()
                    applied = False
                    # B1 : Si le nom du salon contient déjà le préfixe complet (base_prefix + short_lang)
                    for base_prefix, lang_roles in roles_dict.items():
                        full_prefix = (base_prefix + short_lang).lower()
                        if channel_name.startswith(full_prefix) or channel_name.endswith(full_prefix):
                            try:
                                await channel.set_permissions(guild_obj.default_role,
                                                              overwrite=discord.PermissionOverwrite(view_channel=False))
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
                                print(f"Channel {channel.name} configuré avec préfixe complet pour langue {short_lang}")
                            except Exception as e:
                                print(f"Erreur dans la configuration du channel {channel.name} (préfixe complet) : {e}")
                            break
                    # B2 : Si aucune correspondance sur le nom n'a été trouvée,
                    # mais que le salon est dans une catégorie qui a le préfixe de guilde,
                    # on se base sur la langue en DB pour configurer le salon.
                    if not applied and channel.category is not None:
                        matching_base = None
                        cat_name = channel.category.name.lower()
                        for base_prefix in roles_dict:
                            if base_prefix.lower() in cat_name:
                                matching_base = base_prefix
                                break
                        if matching_base is not None:
                            try:
                                await channel.set_permissions(guild_obj.default_role,
                                                              overwrite=discord.PermissionOverwrite(view_channel=False))
                                for lang_code, role in roles_dict[matching_base].items():
                                    if lang_code.upper() == short_lang:
                                        await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=True))
                                    else:
                                        await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(view_channel=False))
                                if channel.overwrites:
                                    for target, overw in channel.overwrites.items():
                                        if isinstance(target, discord.Role) and target not in roles_dict[matching_base].values() and target != guild_obj.default_role:
                                            new_overwrite = overw
                                            new_overwrite.view_channel = None
                                            await channel.set_permissions(target, overwrite=new_overwrite)
                                restored_count += 1
                                applied = True
                                print(f"Channel {channel.name} configuré via catégorie {channel.category.name} pour langue {short_lang}")
                            except Exception as e:
                                print(f"Erreur dans la configuration fallback par catégorie pour channel {channel.name}: {e}")
                    # B3 : Si le salon n'est pas dans une catégorie avec préfixe, on peut appliquer un fallback général
                    if not applied:
                        for base_prefix, lang_roles in roles_dict.items():
                            try:
                                await channel.set_permissions(guild_obj.default_role,
                                                              overwrite=discord.PermissionOverwrite(view_channel=False))
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
                                print(f"Channel {channel.name} fallback général appliqué pour langue {short_lang}")
                            except Exception as e:
                                print(f"Erreur dans le fallback général pour channel {channel.name}: {e}")
                            break
            else:
                print(f"Channel {channel.name} non configuré en DB, ignoré.")

    await interaction.followup.send(f"✅ Permissions synchronisées pour **{restored_count}** salons.", ephemeral=True)


# --- Commande /rollback ---
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
        ch_backup = backup_data.get(str(channel.id))
        # if not ch_backup:
        #     continue
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

# --- Démarrage du bot ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Connecté en tant que {bot.user}.")

# Remplacez "YOUR_BOT_TOKEN" par votre token Discord (veillez à ne pas le divulguer publiquement)
bot.run(TOKEN)
