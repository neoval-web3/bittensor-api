import json
import os
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

# Cette fonction n'est plus nécessaire car nous utilisons get_delegate_identities()
# Gardée pour référence au cas où
def extract_identity_info(delegate) -> Dict[str, Any]:
    """
    DÉPRÉCIÉ: Cette méthode n'est plus utilisée car nous utilisons get_delegate_identities().
    
    Args:
        delegate: Objet délégué de Bittensor
        
    Returns:
        Dict[str, Any]: Dictionnaire contenant les informations d'identité
    """
    identity_info = {
        "name": None,
        "description": None,
        "url": None,
        "image": None,
        "twitter": None
    }
    
    logger.warning("La fonction extract_identity_info est déprécié. Utiliser get_delegate_identities() à la place.")
    
    return identity_info

def fetch_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Récupère les métadonnées des validateurs directement depuis la blockchain Bittensor.
    Utilise get_delegate_identities() pour obtenir les identités complètes.
    Conserve tous les champs avec null comme valeur par défaut.
    
    Returns:
        Dict[str, Dict[str, Any]]: Dictionnaire des métadonnées des validateurs
    """
    try:
        # Initialiser la connexion à Bittensor
        subtensor = init_subtensor()
        
        logger.info("Récupération des métadonnées depuis Bittensor")
        
        # Récupérer la liste des délégués
        delegates = subtensor.get_delegates()
        
        # Récupérer toutes les identités des délégués
        identities = subtensor.get_delegate_identities()
        logger.info(f"Récupération de {len(identities)} identités de délégués")
        
        metadata = {}
        
        for delegate in delegates:
            try:
                # Obtenir les informations de base du délégué
                hotkey = delegate.hotkey_ss58
                coldkey = delegate.owner_ss58
                
                # Structure standard avec valeurs nulles par défaut
                delegate_obj = {
                    "hotkey": hotkey,
                    "coldkey": coldkey,
                    "take": "0.0000000000000000",
                    "verified": False,
                    "name": None,
                    "logo": None,
                    "url": None,
                    "description": None,
                    "verifiedBadge": False,
                    "twitter": None
                }
                
                # Ajouter le take s'il est disponible
                if hasattr(delegate, 'take'):
                    take = float(delegate.take)
                    delegate_obj["take"] = f"{take:.16f}"
                
                # Récupérer l'identité du délégué à partir de la coldkey
                identity = identities.get(coldkey)
                if identity:
                    logger.info(f"Identité trouvée pour {coldkey}: {identity}")
                    
                    # Mettre à jour avec les données réelles si disponibles
                    if hasattr(identity, 'display') and identity.display:
                        delegate_obj["name"] = str(identity.display)
                    
                    if hasattr(identity, 'web') and identity.web:
                        delegate_obj["url"] = str(identity.web)
                    
                    if hasattr(identity, 'image') and identity.image:
                        delegate_obj["logo"] = str(identity.image)
                    
                    if hasattr(identity, 'twitter') and identity.twitter:
                        delegate_obj["twitter"] = str(identity.twitter)
                        
                    # Vérifier si d'autres attributs sont disponibles
                    # On peut ajouter d'autres champs standard ici si nécessaire
                
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
        # Créer le répertoire si nécessaire
        os.makedirs(os.path.dirname(METADATA_FILE), exist_ok=True)
        
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

def inspect_system_structure():
    """
    Fonction de débogage pour inspecter la structure des objets delegate et des identités
    """
    try:
        subtensor = init_subtensor()
        
        # Inspecter les délégués
        delegates = subtensor.get_delegates()
        if delegates:
            sample_delegate = delegates[0]
            logger.info(f"Structure d'un delegate: {dir(sample_delegate)}")
            
            # Afficher les attributs et méthodes disponibles d'un délégué
            for attr in dir(sample_delegate):
                if not attr.startswith('_'):  # Ignorer les attributs privés
                    try:
                        value = getattr(sample_delegate, attr)
                        logger.info(f"Attribut delegate.{attr}: {type(value)} - {value}")
                    except Exception as e:
                        logger.info(f"Impossible d'accéder à l'attribut delegate.{attr}: {e}")
        
        # Inspecter les identités
        identities = subtensor.get_delegate_identities()
        if identities:
            sample_key = next(iter(identities))
            sample_identity = identities[sample_key]
            logger.info(f"Structure d'une identité: {dir(sample_identity)}")
            
            # Afficher les attributs et méthodes disponibles d'une identité
            for attr in dir(sample_identity):
                if not attr.startswith('_'):  # Ignorer les attributs privés
                    try:
                        value = getattr(sample_identity, attr)
                        logger.info(f"Attribut identity.{attr}: {type(value)} - {value}")
                    except Exception as e:
                        logger.info(f"Impossible d'accéder à l'attribut identity.{attr}: {e}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'inspection de la structure: {e}")

if __name__ == "__main__":
    # Inspecter la structure du système pour le débogage
    inspect_system_structure()
    
    # Synchroniser les métadonnées
    sync_metadata()
    
    # Afficher un exemple de validateur
    metadata = load_metadata()
    if metadata:
        # Trouver un validateur avec des métadonnées non vides si possible
        sample_validators = [v for v in metadata.values() 
                           if v.get('name') or v.get('url') or v.get('logo')]
        
        if sample_validators:
            sample_validator = sample_validators[0]
            print(f"Exemple de métadonnées pour un validateur avec identité:")
        else:
            sample_key = next(iter(metadata))
            sample_validator = metadata[sample_key]
            print(f"Exemple de métadonnées pour un validateur (sans identité):")
        
        print(json.dumps(sample_validator, indent=2))
        
        # Compter les validateurs avec des métadonnées d'identité
        validators_with_identity = sum(1 for v in metadata.values() 
                                    if v.get('name') or v.get('url') or v.get('logo'))
        
        print(f"\nNombre total de validateurs: {len(metadata)}")
        print(f"Nombre de validateurs avec identité: {validators_with_identity}")
    else:
        print("Aucune métadonnée trouvée")