!!! There is probably some little issues in APYs calculation !!!

# 🧠 Bittensor API

API FastAPI permettant de récupérer les données des validateurs et des subnets du réseau Bittensor, dans un format compatible avec TaoYield.

---

## 📁 Structure du projet

```
bittensor-api/
├── main.py                # Point d'entrée principal de l'API
├── api.py                 # Déclaration des endpoints FastAPI
├── metadata_sync.py       # Script pour synchroniser les métadonnées des validateurs
├── apy_calculator.py      # Calculs APY à partir des données on-chain
├── requirements.txt       # Dépendances Python
├── docker-compose.yml     # Déploiement via Docker
├── Dockerfile             # Image API + Rust + Python
├── data/                  # Métadonnées statiques (ex: validator_metadata.json)
├── utils/                 # Fonctions utilitaires
├── tao_apy_calculator/        # Code source de TaoYield pour les calculs de rendement
└── .env / env_example     # Variables d'environnement
```

---

## ⚙️ Prérequis

- Python 3.10+
- MongoDB local ou distant
- Docker (optionnel mais recommandé pour un setup rapide)

---

## 📄 Configuration `.env`

Avant de lancer l'API, créez un fichier `.env` à la racine du projet. Vous pouvez utiliser `env_example` comme modèle :

```bash
cp env_example .env
```

Exemple de contenu :

```
NODE_URL=wss://archive.chain.opentensor.ai:443
BATCH_SIZE=100
MONGO_URL=""
```

> 🔒 Si `MONGO_URL` n’est pas défini ou est égal à `mongodb://mongo:27017/`, l’API utilisera automatiquement l’instance MongoDB locale (utile en environnement Docker).

---

## 🚀 Lancement en local (sans Docker)

1. Créez un environnement virtuel et installez les dépendances :

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

2. Lancez l’API :

```bash
python main.py
```

3. Accédez à l'API sur [http://localhost:8000](http://localhost:8000)

---

## 🐳 Lancement avec Docker

> Nécessite Docker et Docker Compose.

1. Build & run l’API avec MongoDB intégré :

```bash
docker-compose up --build
```

2. L’API sera disponible sur [http://localhost:8000](http://localhost:8000)

> 📦 MongoDB tourne dans un conteneur nommé `bittensor-api-mongo`. Les données sont persistées dans le volume `mongo-data`.

---

## 🛠️ Customisation

- Si vous avez déjà une instance MongoDB (locale ou distante), mettez l’URL dans le fichier `.env` :
  ```
  MONGO_URL=mongodb://username:password@host:27017/bittensor-api?authSource=admin
  ```
- Le fallback automatique sur `"mongodb://localhost:27017/"` sera utilisé uniquement si aucun `MONGO_URL` valide n’est fourni.

## API Usage

### TRPC-Compatible Endpoint

The main entry point is a batch endpoint similar to `trpc` usage:
```
GET /api/trpc/delegates.getDelegates4,subnets.getSubnetsNameAndSymbol
```

This returns a batch response with:

- Index `0` = list of validators
- Index `1` = list of known subnets

Query parameters:
- `batch`: Page index (0-based)
- `batch_size`: Number of items per batch (default 32)

**Example:**
```
curl "http://localhost:8000/api/trpc/delegates.getDelegates4,subnets.getSubnetsNameAndSymbol?batch=0&batch_size=32"
```

### REST Endpoints

- `/api/validators`  
  Returns all validators, supports:
  - `sort_by=total_stake|subnet_stake`
  - `sort_order=asc|desc`
  - `subnet_id=XX` (to filter validators active in subnet)
  - `batch=0` and `batch_size=32` for pagination

- `/api/validators/{hotkey}`  
  Returns details for a specific validator

- `/api/validators/subnet/{subnet_id}`  
  Returns validators filtered by subnet

- `/api/subnets`  
  Returns all known subnets with name and symbol

### Admin Endpoint

For updating subnet metadata manually:
```
POST /api/admin/update-subnet
Query params:
- netuid
- name
- symbol
- admin_key (must match ADMIN_KEY in .env)
```

**Example:**
```
curl -X POST "http://localhost:8000/api/admin/update-subnet?netuid=5&name=CustomSubnet&symbol=CS&admin_key=your_key"
```
