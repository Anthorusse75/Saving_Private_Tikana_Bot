import os

def load_gitignore(path):
    """
    Charge les chemins à ignorer depuis un fichier .gitignore.
    """
    gitignore_path = os.path.join(path, '.gitignore')
    if not os.path.exists(gitignore_path):
        return set()

    # Exclure par défaut les fichiers et dossiers spécifiques
    ignored_paths = {
        os.path.join(path, '.git'),
        os.path.join(path, 'flask_session'),
        os.path.join(path, '.gitattributes'),
        os.path.join(path, '.gitignore'),
        os.path.join(path, 'Arborescence.py'),
        os.path.join(path, 'Arborescence.txt'),
        os.path.join(path, 'translator_env'),
    }

    for root, dirs, files in os.walk(path):
        for dir_name in dirs:
            if dir_name == "A_SUPPRIMER" or dir_name == "__pycache__":
                ignored_paths.add(os.path.join(root, dir_name))

    with open(gitignore_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                ignored_paths.add(os.path.join(path, line))
    return ignored_paths

def draw_tree(directory, prefix="", ignored=set(), output_file=None):
    """
    Affiche l'arborescence d'un répertoire en excluant les fichiers/dossiers ignorés.
    """
    entries = [entry for entry in os.listdir(directory) if os.path.join(directory, entry) not in ignored]
    entries.sort()

    for i, entry in enumerate(entries):
        path = os.path.join(directory, entry)
        connector = "├── " if i < len(entries) - 1 else "└── "
        line = f"{prefix}{connector}{entry}\n"
        print(line, end="")
        if output_file:
            output_file.write(line)

        if os.path.isdir(path):
            # Gestion spéciale pour le dossier "flags"
            if os.path.basename(path) == "flags":
                files_in_flags = sorted(os.listdir(path))
                for j, flag_file in enumerate(files_in_flags[:3]):  # Afficher seulement les 3 premiers fichiers
                    sub_connector = "├── " if j < len(files_in_flags[:3]) - 1 else "└── "
                    flag_line = f"{prefix}{connector}{sub_connector}{flag_file}\n"
                    print(flag_line, end="")
                    if output_file:
                        output_file.write(flag_line)
                if len(files_in_flags) > 3:  # Indiquer qu'il y a plus de fichiers
                    more_line = f"{prefix}{connector}    ...\n"
                    print(more_line, end="")
                    if output_file:
                        output_file.write(more_line)
            else:
                new_prefix = prefix + ("│   " if i < len(entries) - 1 else "    ")
                draw_tree(path, new_prefix, ignored, output_file)

def main():
    # Répertoire de base à scanner
    base_directory = os.getcwd()

    # Charger les chemins ignorés
    ignored = load_gitignore(base_directory)

    output_file_path = os.path.join(base_directory, "arborescence.txt")
    with open(output_file_path, "w", encoding="utf-8") as output_file:
        output_file.write(f"Arborescence du répertoire : {base_directory}\n\n")
        print(f"Arborescence du répertoire : {base_directory}\n")
        draw_tree(base_directory, ignored=ignored, output_file=output_file)

    print(f"\nL'arborescence a été sauvegardée dans le fichier : {output_file_path}")

if __name__ == "__main__":
    main()
