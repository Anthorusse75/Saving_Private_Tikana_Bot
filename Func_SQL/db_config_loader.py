# Func_SQL/db_config_loader.py

import os
import json
import platform

def load_db_config():
    """
    Charge la config JSON de la base de données (même code que tu avais avant).
    """
    # Gérer chemin Windows ou Linux
    IS_WINDOWS = (platform.system() == "Windows")
    base_path = "Conf_files\\" if IS_WINDOWS else "Conf_files/"

    # Par exemple, w_db_params.json ou l_db_params.json
    # ou alors tu reprends ton code "db_file = w_db_params if windows else l_db_params"
    # Tu peux faire exactement le même code que dans config.py, mais sans les imports du logger

    db_file = os.path.join(base_path, "w_db_params.json") if IS_WINDOWS else os.path.join(base_path, "l_db_params.json")

    with open(db_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # Option : rename la clé "database" => "db" si tu veux
    data['db'] = data.pop('database', None)
    return data
