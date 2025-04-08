# main.py - Script principal pour l'API Bittensor APY

import os
import json
import time
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import bittensor as bt
import pandas as pd
from pydantic import BaseModel

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration de l'application FastAPI
app = FastAPI(title="Bittensor APY API", description="API pour récupérer les APY des validateurs et subnets Bittensor")

# Permettre les requêtes CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À ajuster en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache pour les données (pour éviter de requêter la blockchain trop souvent)
cache = {
    "delegates": {"data": None, "timestamp": None},
    "subnets": {"data": None, "timestamp": None}
}
CACHE_DURATION = timedelta(minutes=5)  # Rafraîchir les données toutes les 5 minutes

# Configuration de Bittensor
bt.logging.set_trace(False)
subtensor = bt.subtensor(network="finney")  # Pour le mainnet, utilisez "finney"

def init_subtensor():
    """Initialise la connexion au réseau Bittensor."""
    logger.info("Initialisation de la connexion au réseau Bittensor...")
    try:
        global subtensor
        subtensor = bt.subtensor(network="finney")
        logger.info(f"Connecté au réseau Bittensor: {subtensor.network}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la connexion au réseau Bittensor: {e}")
        return False

def calculate_apy(emissions: float, stake: float) -> float:
    """
    Calcule l'APY basé sur les émissions et les stakes.
    
    Args:
        emissions: Émissions quotidiennes en TAO
        stake: Montant staké en TAO
        
    Returns:
        float: APY en pourcentage
    """
    if stake == 0:
        return 0.0
    
    daily_rate = emissions / stake
    compounded_yearly = (1 + daily_rate) ** 365 - 1
    
    # Convertir en pourcentage et arrondir à 2 décimales
    return round(compounded_yearly * 100, 2)

async def get_delegates_data() -> Dict:
    """
    Récupère les données des délégués/validateurs avec les APY calculés.
    
    Returns:
        Dict: Données des délégués au format compatible avec l'API taoyield
    """
    # Vérifier le cache
    if cache["delegates"]["data"] is not None and cache["delegates"]["timestamp"] is not None:
        if datetime.now() - cache["delegates"]["timestamp"] < CACHE_DURATION:
            return cache["delegates"]["data"]
    
    try:
        # Récupérer les informations sur les émissions par subnet
        emissions_by_subnet = await get_subnet_emissions()
        
        # Récupérer la liste des délégués
        delegates = subtensor.get_delegates()
        
        result_delegates = []
        
        for delegate in delegates:
            try:
                # Obtenir les informations de base du délégué
                hotkey = delegate.hotkey_ss58
                owner = delegate.owner_ss58
                
                stake_dict = {}
                subnet_apy_dict = {}
                total_staked = 0.0
                
                # Calculer le total des stakes
                for netuid, stake_info in delegate.total_stake.items():
                    netuid_str = str(netuid)
                    
                    # Le stake_info est un objet Balance 
                    # Utiliser l'attribut tao qui est plus simple à gérer
                    if hasattr(stake_info, 'tao'):
                        stake_tao = float(stake_info.tao)
                    elif hasattr(stake_info, 'rao'):
                        # Fallback sur rao si tao n'est pas disponible
                        stake_tao = float(stake_info.rao) / 1e9
                    else:
                        # Si ni tao ni rao n'est disponible, essayer de convertir directement
                        try:
                            stake_tao = float(stake_info) / 1e9
                        except (ValueError, TypeError):
                            logger.warning(f"Impossible de convertir stake: {stake_info}")
                            stake_tao = 0.0
                    
                    if stake_tao > 0:
                        stake_dict[netuid_str] = stake_tao
                        total_staked += stake_tao
                        
                        # Calculer l'APY pour ce subnet s'il est enregistré
                        if hasattr(delegate, 'registrations') and int(netuid) in delegate.registrations:
                            daily_emission = emissions_by_subnet.get(int(netuid), 0)
                            apy = calculate_apy(daily_emission, stake_tao)
                            subnet_apy_dict[netuid_str] = apy
                
                # Calculer l'APY total (moyenne pondérée des APY par subnet)
                total_apy = 0.0
                if total_staked > 0:
                    for netuid, stake in stake_dict.items():
                        subnet_apy = subnet_apy_dict.get(netuid, 0)
                        weight = stake / total_staked
                        total_apy += subnet_apy * weight
                
                # Calculer le total des tokens délégués
                total_delegated = 0.0
                for nominator, nominators_by_subnet in delegate.nominators.items():
                    for subnet_id, stake_info in nominators_by_subnet.items():
                        # Traiter l'objet Balance pour les nominateurs
                        if hasattr(stake_info, 'tao'):
                            nominator_tao = float(stake_info.tao)
                        elif hasattr(stake_info, 'rao'):
                            nominator_tao = float(stake_info.rao) / 1e9
                        else:
                            try:
                                nominator_tao = float(stake_info) / 1e9
                            except (ValueError, TypeError):
                                logger.warning(f"Impossible de convertir nominator stake: {stake_info}")
                                nominator_tao = 0.0
                                
                        total_delegated += nominator_tao
                
                # Calculer l'APY pour les nominateurs (en tenant compte du take)
                take_percentage = float(delegate.take) * 100  # Convertir en pourcentage
                nominator_apy = total_apy * (1 - take_percentage / 100)
                
                # Déterminer quels subnets ont des validator_permits
                validator_permits = []
                if hasattr(delegate, 'validator_permits'):
                    validator_permits = delegate.validator_permits
                
                # Construire l'objet délégué
                delegate_obj = {
                    "hotkey": hotkey,
                    "coldkey": owner,
                    "nominator": owner,
                    "name": f"Validator {hotkey[:8]}",
                    "description": "",
                    "blockRegisteredNeuron": 0,
                    "blockLastUpdated": 0,
                    "registeredWallet": owner,
                    "take": take_percentage,
                    "validatorPermit": len(validator_permits) > 0,
                    "totalDelegated": total_delegated,
                    "staked": stake_dict,
                    "totalStaked": total_staked,
                    "apy": round(total_apy, 2),
                    "subnet": subnet_apy_dict,
                    "nominatorApy": round(nominator_apy, 2),
                    "totalNominated": total_delegated,
                    "delegateRate": take_percentage,
                    "ownerApyShare": 50,
                    "totalVtrust": 0
                }
                
                result_delegates.append(delegate_obj)
            except Exception as delegate_error:
                logger.error(f"Erreur lors du traitement du délégué {delegate.hotkey_ss58}: {delegate_error}")
                # Continuer avec le prochain délégué
        
        # Mettre à jour le cache
        delegates_data = {"delegates": result_delegates}
        cache["delegates"] = {
            "data": delegates_data,
            "timestamp": datetime.now()
        }
        
        return delegates_data
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des données des délégués: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def get_subnet_emissions() -> Dict[int, float]:
    """
    Récupère les émissions quotidiennes pour chaque subnet.
    
    Returns:
        Dict[int, float]: Dictionnaire avec netuid comme clé et émissions quotidiennes comme valeur
    """
    emissions_dict = {}
    
    try:
        # Récupérer tous les subnets - cette méthode retourne le nombre de subnets, pas une liste
        num_subnets = subtensor.get_subnets()
        
        if isinstance(num_subnets, int):
            # C'est un entier qui représente le nombre de subnets
            logger.info(f"Nombre de subnets détectés: {num_subnets}")
            
            # Parcourir chaque subnet par son index
            for netuid in range(num_subnets):
                try:
                    # Tenter d'obtenir les émissions pour ce subnet
                    emission_value = subtensor.get_emission_value_by_subnet(netuid=netuid)
                    
                    # Convertir en TAO et calculer la valeur quotidienne
                    emissions_per_day = float(emission_value) * 7200 / 1e9  # en TAO par jour
                    emissions_dict[netuid] = emissions_per_day
                    logger.info(f"Émission pour subnet {netuid}: {emissions_per_day} TAO/jour")
                except Exception as e:
                    logger.warning(f"Erreur lors de la récupération des émissions pour le subnet {netuid}: {e}")
                    emissions_dict[netuid] = 0.01  # Valeur par défaut
        else:
            # Dans le cas improbable où ce ne serait pas un entier
            logger.warning(f"Type inattendu pour get_subnets(): {type(num_subnets)}")
            
            # Sécurité: fournir quelques valeurs par défaut
            for i in range(20):  # Supposer jusqu'à 20 subnets
                emissions_dict[i] = 0.01
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des émissions: {e}")
        
        # Fournir quelques valeurs par défaut
        for i in range(20):  # Supposer jusqu'à 20 subnets
            emissions_dict[i] = 0.01
    
    return emissions_dict
@app.get("/api/debug/delegates")
async def debug_delegates():
    delegates = subtensor.get_delegates()
    delegate_info = []
    
    for delegate in delegates:
        # Convertir l'objet en dictionnaire de ses attributs disponibles
        delegate_dict = {attr: getattr(delegate, attr) for attr in dir(delegate) 
                        if not attr.startswith('_') and not callable(getattr(delegate, attr))}
        delegate_info.append(delegate_dict)
    
    return {"delegates": delegate_info[:2]}  # Renvoie les 2 premiers pour limiter la taille

async def get_subnet_emissions() -> Dict[int, float]:
    """
    Récupère les émissions quotidiennes pour chaque subnet.
    
    Returns:
        Dict[int, float]: Dictionnaire avec netuid comme clé et émissions quotidiennes comme valeur
    """
    emissions_dict = {}
    
    try:
        # Récupérer tous les subnets
        subnets = subtensor.get_subnets()
        
        # Vérifier le type de subnets pour adapter le traitement
        if isinstance(subnets, list):
            for subnet in subnets:
                # Vérifier si subnet est un dictionnaire ou un objet
                if isinstance(subnet, dict):
                    netuid = subnet['netuid']
                else:
                    netuid = subnet.netuid
                
                try:
                    # Tenter d'obtenir les émissions pour ce subnet
                    emission_value = subtensor.get_emission_value_by_subnet(netuid=netuid)
                    
                    # Convertir en TAO et calculer la valeur quotidienne
                    emissions_per_day = float(emission_value) * 7200 / 1e9  # en TAO par jour
                    emissions_dict[netuid] = emissions_per_day
                    
                except Exception as e:
                    logger.warning(f"Erreur lors de la récupération des émissions pour le subnet {netuid}: {e}")
                    emissions_dict[netuid] = 0.01  # Valeur par défaut
        else:
            # Si subnets est un entier (nombre de subnets)
            for netuid in range(subnets):
                try:
                    emission_value = subtensor.get_emission_value_by_subnet(netuid=netuid)
                    emissions_per_day = float(emission_value) * 7200 / 1e9
                    emissions_dict[netuid] = emissions_per_day
                except Exception as e:
                    logger.warning(f"Erreur pour le subnet {netuid}: {e}")
                    emissions_dict[netuid] = 0.01
            
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des émissions: {e}")
        # Fournir quelques valeurs par défaut
        for i in range(20):  # Supposer jusqu'à 20 subnets
            emissions_dict[i] = 0.01
    
    return emissions_dict
async def get_subnets_data() -> Dict:
    """
    Récupère les informations sur les subnets.
    
    Returns:
        Dict: Données des subnets au format compatible avec l'API taoyield
    """
    # Vérifier le cache
    if cache["subnets"]["data"] is not None and cache["subnets"]["timestamp"] is not None:
        if datetime.now() - cache["subnets"]["timestamp"] < CACHE_DURATION:
            return cache["subnets"]["data"]
    
    try:
        # Récupérer le nombre de subnets
        num_subnets = subtensor.get_subnets()
        logger.info(f"Nombre de subnets: {num_subnets}")
        
        result_subnets = []
        
        # Parcourir tous les subnets par index
        for netuid in range(num_subnets):
            try:
                # Tenter de récupérer plus d'informations sur ce subnet
                subnet_info = None
                try:
                    subnet_info = subtensor.get_subnet_info(netuid=netuid)
                except Exception as subnet_error:
                    logger.warning(f"Impossible de récupérer les informations pour le subnet {netuid}: {subnet_error}")
                
                # Définir un nom par défaut
                name = f"Subnet {netuid}"
                
                # Essayer de récupérer un nom plus spécifique si possible
                if subnet_info is not None:
                    if hasattr(subnet_info, 'name') and subnet_info.name:
                        name = subnet_info.name
                
                # Symbole par défaut basé sur le netuid
                symbol = f"SN{netuid}"
                
                # Créer l'objet subnet
                subnet_obj = {
                    "netuid": netuid,
                    "name": name,
                    "symbol": symbol
                }
                
                result_subnets.append(subnet_obj)
                
            except Exception as e:
                logger.warning(f"Erreur pour le subnet {netuid}: {e}")
                # Ajouter quand même le subnet avec des informations minimales
                result_subnets.append({
                    "netuid": netuid,
                    "name": f"Subnet {netuid}",
                    "symbol": f"SN{netuid}"
                })
        
        # Mettre à jour le cache
        subnets_data = {"subnets": result_subnets}
        cache["subnets"] = {
            "data": subnets_data,
            "timestamp": datetime.now()
        }
        
        return subnets_data
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des données des subnets: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# Endpoints de l'API

@app.get("/api/status")
async def get_status():
    """Vérifier si l'API est opérationnelle."""
    return {"status": "online", "timestamp": datetime.now().isoformat()}

@app.get("/api/trpc/delegates.getDelegates4")
async def get_delegates():
    """Récupère les données des délégués (validators) avec leurs APY."""
    try:
        data = await get_delegates_data()
        return JSONResponse(content={"result": {"data": data}})
    except Exception as e:
        logger.error(f"Erreur lors de la réponse à la requête getDelegates4: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trpc/subnets.getSubnetsNameAndSymbol")
async def get_subnets():
    """Récupère les informations sur les subnets."""
    try:
        data = await get_subnets_data()
        return JSONResponse(content={"result": {"data": data}})
    except Exception as e:
        logger.error(f"Erreur lors de la réponse à la requête getSubnetsNameAndSymbol: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/trpc/delegates.getDelegates4,subnets.getSubnetsNameAndSymbol")
async def get_batch():
    """Endpoint pour récupérer les délégués et les subnets en une seule requête (batch)."""
    try:
        delegates_data = await get_delegates_data()
        subnets_data = await get_subnets_data()
        
        return JSONResponse(content={
            "0": {"result": {"data": delegates_data}},
            "1": {"result": {"data": subnets_data}}
        })
    except Exception as e:
        logger.error(f"Erreur lors de la réponse à la requête batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debug/apy")
async def debug_apy():
    """Endpoint de débogage pour vérifier le calcul des APY et les types des objets."""
    try:
        # Récupérer les émissions
        emissions = await get_subnet_emissions()
        
        # Récupérer un délégué pour test
        delegates = subtensor.get_delegates()
        if not delegates or len(delegates) == 0:
            return {"error": "Aucun délégué trouvé"}
        
        delegate = delegates[0]
        
        # Informations sur le délégué
        delegate_info = {
            "hotkey": delegate.hotkey_ss58,
            "owner": delegate.owner_ss58,
            "take": delegate.take
        }
        
        # Informations sur les stakes
        stakes_info = {}
        for netuid, stake in delegate.total_stake.items():
            stakes_info[str(netuid)] = {
                "stake_type": type(stake).__name__,
                "stake_dir": dir(stake) if hasattr(stake, '__dir__') else "No dir available",
                "stake_value": str(stake)
            }
        
        # Informations sur les nominateurs
        nominators_info = {}
        for nominator, subnets in delegate.nominators.items():
            nominators_info[nominator] = {}
            for subnet, stake in subnets.items():
                nominators_info[nominator][str(subnet)] = {
                    "stake_type": type(stake).__name__,
                    "stake_dir": dir(stake) if hasattr(stake, '__dir__') else "No dir available",
                    "stake_value": str(stake)
                }
        
        # Emissions récupérées
        emissions_info = {str(netuid): emission for netuid, emission in emissions.items()}
        
        # Calculer quelques APY de test
        apy_tests = {}
        for emission_amount in [0.1, 1.0, 10.0]:
            for stake_amount in [10.0, 100.0, 1000.0]:
                test_key = f"emission_{emission_amount}_stake_{stake_amount}"
                apy_tests[test_key] = calculate_apy(emission_amount, stake_amount)
        
        return {
            "delegate_info": delegate_info,
            "stakes_info": stakes_info,
            "nominators_info": nominators_info,
            "emissions_info": emissions_info,
            "apy_tests": apy_tests
        }
        
    except Exception as e:
        logger.error(f"Erreur dans le debug APY: {e}")
        return {"error": str(e)}
if __name__ == "__main__":
    # Initialiser la connexion à Bittensor
    if not init_subtensor():
        logger.error("Impossible de se connecter au réseau Bittensor. Arrêt du programme.")
        exit(1)
    
    # Démarrer le serveur
    uvicorn.run(app, host="0.0.0.0", port=8000)