import json
import os
import re
import logging
import bittensor as bt
from typing import Dict, Any, Optional

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Chemin du fichier de métadonnées local
METADATA_FILE = "data/validator_metadata.json"

def init_subtensor():
    """
    Initialise la connexion au réseau Bittensor.
    
    Returns:
        bt.subtensor: Instance de connexion au réseau Bittensor
    """
    logger.info("Initialisation de la connexion au réseau Bittensor...")
    try:
        subtensor = bt.subtensor(network="finney")  # Pour le mainnet
        logger.info(f"Connecté au réseau Bittensor: {subtensor.network}")
        return subtensor
    except Exception as e:
        logger.error(f"Erreur lors de la connexion au réseau Bittensor: {e}")
        raise

def parse_chain_identity(identity_str: str) -> Dict[str, Any]:
    """
    Parse une chaîne de caractères ChainIdentity en dictionnaire.
    
    Args:
        identity_str: Chaîne de caractères représentant une ChainIdentity
        
    Returns:
        Dict[str, Any]: Dictionnaire contenant les informations de l'identité
    """
    if not identity_str or not isinstance(identity_str, str) or not identity_str.startswith("ChainIdentity"):
        return {"name": identity_str}
    
    # Extraire les paires clé-valeur à l'aide d'expressions régulières
    pattern = r"(\w+)='([^']*)'"
    matches = re.findall(pattern, identity_str)
    
    identity = {}
    for key, value in matches:
        identity[key] = value if value else None
    
    return identity

def fetch_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Récupère les métadonnées des validateurs directement depuis la blockchain Bittensor.
    
    Returns:
        Dict[str, Dict[str, Any]]: Dictionnaire des métadonnées des validateurs
    """
    try:
        # Initialiser la connexion à Bittensor
        subtensor = init_subtensor()
        
        logger.info("Récupération des métadonnées depuis Bittensor")
        
        # Récupérer la liste des délégués
        delegates = subtensor.get_delegates()
        
        metadata = {}
        
        for delegate in delegates:
            try:
                # Obtenir les informations de base du délégué
                hotkey = delegate.hotkey_ss58
                coldkey = delegate.owner_ss58
                
                # Essayer de récupérer le nom ou l'identité
                name = f"Validator {hotkey[:8]}"
                description = "Validator on Bittensor network"
                url = None
                logo = None
                
                # Essayer de récupérer le ChainIdentity si disponible
                try:
                    if hasattr(delegate, 'identity') and delegate.identity:
                        identity_str = str(delegate.identity)
                        identity = parse_chain_identity(identity_str)
                        
                        if "name" in identity and identity["name"]:
                            name = identity["name"]
                        
                        if "description" in identity and identity["description"]:
                            description = identity["description"]
                        
                        if "url" in identity and identity["url"]:
                            url = identity["url"]
                        
                        if "image" in identity and identity["image"]:
                            logo = identity["image"]
                except Exception as identity_error:
                    logger.warning(f"Erreur lors de la récupération de l'identité pour {hotkey}: {identity_error}")
                
                # Calculer le take en format string
                take = 0.0
                if hasattr(delegate, 'take'):
                    take = float(delegate.take)
                take_str = f"{take:.16f}"
                
                # Construire l'objet délégué (métadonnées uniquement)
                delegate_obj = {
                    "hotkey": hotkey,
                    "coldkey": coldkey,
                    "take": take_str,
                    "verified": False,  # Par défaut, à mettre à jour manuellement si nécessaire
                    "name": name,
                    "logo": logo,
                    "url": url,
                    "description": description,
                    "verifiedBadge": False,  # Par défaut, à mettre à jour manuellement si nécessaire
                    "twitter": None
                }
                
                # Ajouter le délégué au dictionnaire
                metadata[hotkey] = delegate_obj
                
            except Exception as delegate_error:
                logger.error(f"Erreur lors du traitement du délégué {getattr(delegate, 'hotkey_ss58', 'unknown')}: {delegate_error}")
        
        logger.info(f"Récupération réussie: {len(metadata)} validateurs trouvés")
        return metadata
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des métadonnées Bittensor: {e}")
        return {}

def save_metadata(metadata: Dict[str, Dict[str, Any]]) -> bool:
    """
    Sauvegarde les métadonnées dans un fichier JSON.
    
    Args:
        metadata: Dictionnaire des métadonnées des validateurs
        
    Returns:
        bool: True si la sauvegarde a réussi, False sinon
    """
    try:
        with open(METADATA_FILE, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Métadonnées sauvegardées dans {METADATA_FILE}: {len(metadata)} validateurs")
        return True
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Erreur lors de la sauvegarde des métadonnées: {e}")
        return False

def load_metadata() -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Charge les métadonnées depuis le fichier local.
    
    Returns:
        Optional[Dict[str, Dict[str, Any]]]: Dictionnaire des métadonnées des validateurs ou None en cas d'erreur
    """
    if not os.path.exists(METADATA_FILE):
        logger.warning(f"Fichier de métadonnées {METADATA_FILE} introuvable")
        return None
    
    try:
        with open(METADATA_FILE, 'r') as f:
            metadata = json.load(f)
        
        logger.info(f"Métadonnées chargées depuis {METADATA_FILE}: {len(metadata)} validateurs")
        return metadata
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Erreur lors du chargement des métadonnées: {e}")
        return None

def get_validator_metadata(hotkey: str) -> Optional[Dict[str, Any]]:
    """
    Récupère les métadonnées d'un validateur spécifique par sa hotkey.
    
    Args:
        hotkey: Hotkey du validateur
        
    Returns:
        Optional[Dict[str, Any]]: Métadonnées du validateur ou None si non trouvé
    """
    # Charger les métadonnées locales
    metadata = load_metadata()
    
    # Si aucune métadonnée locale n'est disponible, récupérer de Bittensor
    if metadata is None:
        metadata = fetch_metadata()
        save_metadata(metadata)
    
    # Rechercher par hotkey
    return metadata.get(hotkey)

def sync_metadata() -> bool:
    """
    Synchronise les métadonnées depuis Bittensor.
    
    Returns:
        bool: True si la synchronisation a réussi, False sinon
    """
    try:
        # Récupérer les métadonnées
        metadata = fetch_metadata()
        
        # Sauvegarder les métadonnées
        success = save_metadata(metadata)
        
        logger.info("Synchronisation des métadonnées terminée")
        return success
    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation des métadonnées: {e}")
        return False

if __name__ == "__main__":
    # Synchroniser les métadonnées
    sync_metadata()
    
    # Afficher un exemple de validateur
    metadata = load_metadata()
    if metadata:
        sample_key = next(iter(metadata))
        sample_validator = metadata[sample_key]
        print(f"Exemple de métadonnées pour {sample_validator['name']}:")
        print(json.dumps(sample_validator, indent=2))
        
        print(f"\nNombre total de validateurs: {len(metadata)}")
    else:
        print("Aucune métadonnée trouvée")