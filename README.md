# Bittensor APY API

## Description

Cette API permet de récupérer et d'exposer les données de rendement (APY) des validateurs et subnets du réseau Bittensor, similaire à celle utilisée par taoyield.com. Elle utilise le SDK Bittensor pour communiquer directement avec la blockchain et calculer les APY pour chaque validateur et subnet.

## Fonctionnalités

- Récupération des données de tous les validateurs avec leurs APY
- Récupération des informations sur tous les subnets
- Calcul précis des APY basé sur les émissions et les stakes
- Système de cache pour optimiser les performances
- Endpoints de débogage pour faciliter le développement

## Prérequis

- Python 3.8+
- pip (gestionnaire de paquets Python)
- Accès à internet pour communiquer avec le réseau Bittensor

## Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/votre-username/bittensor-apy-api.git
cd bittensor-apy-api
```

### 2. Créer un environnement virtuel

```bash
# Créer un environnement virtuel
python -m venv env

# Activer l'environnement virtuel
# Sur Windows
env\Scripts\activate
# Sur macOS/Linux
source env/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

## Utilisation

### Démarrer l'API

```bash
python api.py
```

L'API sera accessible à l'adresse `http://localhost:8000`.

### Endpoints disponibles

- **GET /api/status** - Vérifier si l'API est opérationnelle
- **GET /api/trpc/delegates.getDelegates4** - Récupérer les données des délégués
- **GET /api/trpc/subnets.getSubnetsNameAndSymbol** - Récupérer les informations sur les subnets
- **GET /api/trpc/delegates.getDelegates4,subnets.getSubnetsNameAndSymbol** - Récupérer les délégués et les subnets en une seule requête

### Endpoints de débogage

- **GET /api/debug/delegates** - Examiner la structure des délégués
- **GET /api/debug/subnets** - Examiner la structure des subnets
- **GET /api/debug/apy** - Examiner le calcul des APY

## Déploiement

### Avec Docker

1. Construire l'image Docker
```bash
docker build -t bittensor-apy-api .
```

2. Exécuter le conteneur
```bash
docker run -d -p 8000:8000 --name bittensor-api bittensor-apy-api
```

### Avec Docker Compose

```bash
docker-compose up -d
```

## Configuration

La configuration de l'API peut être modifiée dans le fichier `api.py` :

- **CACHE_DURATION** - Durée de validité du cache (par défaut : 5 minutes)
- **Réseau Bittensor** - Mainnet (`"finney"`) ou testnet (`"nobunaga"`)

## Structure de la réponse API

Voici un exemple de la structure de données renvoyée par l'endpoint principal :

```json
{
    "0": {
        "result": {
            "data": {
                "delegates": [
                    {
                        "hotkey": "5FEYsPgLA22e41THYyH4waiMHRDYrjQUxr6dDwmuZ3DPxtuP",
                        "coldkey": "5F953EH5EVc9BUKYLhktAdzH1waVdgEtwyh5ygTrwCuJkwML",
                        "nominator": "5F953EH5EVc9BUKYLhktAdzH1waVdgEtwyh5ygTrwCuJkwML",
                        "name": "Validator 5FEYsPgL",
                        "take": 17.9995422293431,
                        "validatorPermit": true,
                        "totalDelegated": 2392.9784102709996,
                        "staked": {
                            "39": 2392.976335057,
                            "0": 0.002075214
                        },
                        "totalStaked": 2392.978410271,
                        "apy": 0.15,
                        "subnet": {
                            "39": 0.15
                        },
                        "nominatorApy": 0.12
                    }
                ]
            }
        }
    },
    "1": {
        "result": {
            "data": {
                "subnets": [
                    {
                        "netuid": 0,
                        "name": "Subnet 0",
                        "symbol": "SN0"
                    },
                    {
                        "netuid": 1,
                        "name": "Subnet 1",
                        "symbol": "SN1"
                    }
                ]
            }
        }
    }
}
```

## Maintenance

Pour mettre à jour les dépendances :

```bash
pip install --upgrade -r requirements.txt
```

## Dépannage

Si vous rencontrez des problèmes, vérifiez les logs du serveur et utilisez les endpoints de débogage pour diagnostiquer les problèmes.

## Licence

MIT
