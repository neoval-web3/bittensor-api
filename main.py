import asyncio
import threading
import json
from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import time
import os
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

# Chargement des variables d'environnement
load_dotenv()

# Connexion MongoDB
MONGO_URL = os.getenv("MONGO_URL")
print("MONGO_URL: ", MONGO_URL)
if not MONGO_URL:
    print("⚠️ Defaulting to internal Docker MongoDB...")
    MONGO_URL = "mongodb://localhost:27017/" if os.environ.get("USE_LOCAL_MONGO") else "mongodb://mongo:27017/"
else:
    print("✅ Using external MongoDB:", MONGO_URL)

print(f"Using MongoDB URL: {MONGO_URL}")
client = MongoClient(MONGO_URL)
db = client["bittensor-api"]
validators_collection = db["yield"]

# Create subnets collection if it doesn't exist
try:
    subnets_collection = db.create_collection("subnets")
    print("Created subnets collection")
except CollectionInvalid:
    # Collection already exists
    subnets_collection = db["subnets"]
    print("Using existing subnets collection")

# Intervalle en secondes pour la mise à jour
UPDATE_METADATA_INTERVAL = 3600  # 1 heure
UPDATE_APY_INTERVAL = 1800       # 30 minutes

# --- FONCTIONS DE MISE À JOUR (APPELLES EN BACKGROUND) ---

def run_metadata_updater():
    while True:
        try:
            print(f"[{datetime.now()}] Running metadata updater...")
            os.system("python metadata_sync.py")
            print(f"[{datetime.now()}] Metadata update completed")
        except Exception as e:
            print(f"[{datetime.now()}] Error in metadata updater: {e}")
        time.sleep(UPDATE_METADATA_INTERVAL)

def run_apy_updater():
    while True:
        try:
            print(f"[{datetime.now()}] Running APY calculator...")
            os.system("python apy_calculator.py")
            print(f"[{datetime.now()}] APY calculation completed")
        except Exception as e:
            print(f"[{datetime.now()}] Error in APY updater: {e}")
        time.sleep(UPDATE_APY_INTERVAL)

# --- FONCTIONS UTILITAIRES ---

def calculate_total_stake(validator_doc):
    """Calculate total stake across all subnets for a validator."""
    total_stake = 0
    subnets_data = validator_doc.get("subnetsData", {})
    
    for subnet_id, subnet_data in subnets_data.items():
        latest_stake = subnet_data.get("latestStake")
        if latest_stake and latest_stake.isdigit():
            total_stake += int(latest_stake)
    
    return total_stake

def get_subnet_stake(validator_doc, subnet_id):
    """Get stake for a specific subnet, or 0 if not present."""
    subnets_data = validator_doc.get("subnetsData", {})
    subnet_data = subnets_data.get(str(subnet_id), {})
    latest_stake = subnet_data.get("latestStake", "0")
    
    if latest_stake and latest_stake.isdigit():
        return int(latest_stake)
    return 0

def aggregate_subnet_data(validator_doc):
    """Aggregate data across all subnets to get top-level metrics."""
    subnets_data = validator_doc.get("subnetsData", {})
    
    # Initialize aggregated values
    latest_stake_total = 0
    stake_1h_ago_total = 0
    stake_24h_ago_total = 0
    stake_7d_ago_total = 0
    stake_30d_ago_total = 0
    
    hourly_yield_total = 0
    daily_yield_total = 0
    weekly_yield_total = 0
    monthly_yield_total = 0
    
    # Count how many subnets have data for each time period for avg calculation
    hourly_count = 0
    daily_count = 0
    weekly_count = 0
    monthly_count = 0
    
    # Aggregate data from all subnets
    for subnet_id, subnet_data in subnets_data.items():
        # Aggregate stake data
        if subnet_data.get("latestStake") and subnet_data["latestStake"].isdigit():
            latest_stake_total += int(subnet_data["latestStake"])
        
        if subnet_data.get("stake1hAgo") and subnet_data["stake1hAgo"].isdigit():
            stake_1h_ago_total += int(subnet_data["stake1hAgo"])
            hourly_count += 1
        
        if subnet_data.get("stake24hAgo") and subnet_data["stake24hAgo"].isdigit():
            stake_24h_ago_total += int(subnet_data["stake24hAgo"])
            daily_count += 1
        
        if subnet_data.get("stake7dAgo") and subnet_data["stake7dAgo"].isdigit():
            stake_7d_ago_total += int(subnet_data["stake7dAgo"])
            weekly_count += 1
        
        if subnet_data.get("stake30dAgo") and subnet_data["stake30dAgo"].isdigit():
            stake_30d_ago_total += int(subnet_data["stake30dAgo"])
            monthly_count += 1
        
        # Aggregate yield data
        if subnet_data.get("hourlyYield") and subnet_data["hourlyYield"].isdigit():
            hourly_yield_total += int(subnet_data["hourlyYield"])
        
        if subnet_data.get("dailyYield") and subnet_data["dailyYield"].isdigit():
            daily_yield_total += int(subnet_data["dailyYield"])
        
        if subnet_data.get("weeklyYield") and subnet_data["weeklyYield"].isdigit():
            weekly_yield_total += int(subnet_data["weeklyYield"])
        
        if subnet_data.get("monthlyYield") and subnet_data["monthlyYield"].isdigit():
            monthly_yield_total += int(subnet_data["monthlyYield"])
    
    # Calculate APYs
    hourly_apy = None
    daily_apy = None
    weekly_apy = None
    monthly_apy = None
    
    if hourly_count > 0 and stake_1h_ago_total > 0:
        hourly_yield_annualized = hourly_yield_total * 24 * 365
        hourly_apy = round((hourly_yield_annualized / stake_1h_ago_total) * 100, 2)
    
    if daily_count > 0 and stake_24h_ago_total > 0:
        daily_yield_annualized = daily_yield_total * 365
        daily_apy = round((daily_yield_annualized / stake_24h_ago_total) * 100, 2)
    
    if weekly_count > 0 and stake_7d_ago_total > 0:
        weekly_yield_annualized = weekly_yield_total * (365 / 7)
        weekly_apy = round((weekly_yield_annualized / stake_7d_ago_total) * 100, 2)
    
    if monthly_count > 0 and stake_30d_ago_total > 0:
        monthly_yield_annualized = monthly_yield_total * (365 / 30)
        monthly_apy = round((monthly_yield_annualized / stake_30d_ago_total) * 100, 2)
    
    return {
        "latestStake": str(latest_stake_total) if latest_stake_total > 0 else None,
        "stake1hAgo": str(stake_1h_ago_total) if stake_1h_ago_total > 0 else None,
        "stake24hAgo": str(stake_24h_ago_total) if stake_24h_ago_total > 0 else None,
        "stake7dAgo": str(stake_7d_ago_total) if stake_7d_ago_total > 0 else None,
        "stake30dAgo": str(stake_30d_ago_total) if stake_30d_ago_total > 0 else None,
        "hourlyYield": str(hourly_yield_total) if hourly_yield_total > 0 else None,
        "dailyYield": str(daily_yield_total) if daily_yield_total > 0 else None,
        "weeklyYield": str(weekly_yield_total) if weekly_yield_total > 0 else None,
        "monthlyYield": str(monthly_yield_total) if monthly_yield_total > 0 else None,
        "hourlyApy": str(hourly_apy) if hourly_apy is not None else None,
        "dailyApy": str(daily_apy) if daily_apy is not None else None,
        "weeklyApy": str(weekly_apy) if weekly_apy is not None else None,
        "monthlyApy": str(monthly_apy) if monthly_apy is not None else None
    }

# --- SERVEUR FASTAPI POUR EXPOSER LES DONNÉES ---

app = FastAPI(title="Bittensor Validators API", 
              description="API to retrieve Bittensor validator data with sorting options",
              version="1.0.0")

# Autoriser toutes les origines (pour test local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- STANDARD API ENDPOINTS ---

@app.get("/api/validators")
def get_validators(
    sort_by: str = "total_stake",
    sort_order: str = "desc",
    subnet_id: Optional[int] = None,
    limit: Optional[int] = None,
    batch: Optional[int] = None,
    batch_size: int = 32
):
    """
    Get validators with various filtering and sorting options.
    
    Args:
        sort_by: Field to sort by (total_stake or subnet_stake)
        sort_order: Sort order (asc or desc)
        subnet_id: Filter by specific subnet
        limit: Limit total results
        batch: Batch number (0-based) to retrieve
        batch_size: Size of each batch (default: 32)
    """
    # Récupère tous les documents sans le champ "_id"
    docs = list(validators_collection.find({}, {"_id": 0}))
    
    # Calculate total stake for each validator and add it as a field
    for doc in docs:
        doc["total_stake"] = calculate_total_stake(doc)
        
        # If a subnet_id is specified, add the specific subnet stake for sorting
        if subnet_id is not None:
            doc["subnet_stake"] = get_subnet_stake(doc, subnet_id)
    
    # Sort the validators
    if sort_by == "total_stake":
        docs.sort(key=lambda x: x.get("total_stake", 0), reverse=(sort_order.lower() == "desc"))
    elif sort_by == "subnet_stake" and subnet_id is not None:
        docs.sort(key=lambda x: x.get("subnet_stake", 0), reverse=(sort_order.lower() == "desc"))
    
    # Filter by subnet if specified
    if subnet_id is not None:
        docs = [doc for doc in docs if get_subnet_stake(doc, subnet_id) > 0]
    
    # Get total count before pagination
    total_count = len(docs)
    
    # Apply batching if specified
    if batch is not None and isinstance(batch, int) and batch >= 0:
        start_idx = batch * batch_size
        end_idx = start_idx + batch_size
        docs = docs[start_idx:end_idx]
    # Otherwise apply limit if specified
    elif limit is not None and isinstance(limit, int) and limit > 0:
        docs = docs[:limit]

    formatted_docs = []
    for doc in docs:
        # Only include validators with at least one subnet if filtering by subnet
        if subnet_id is not None and doc.get("subnet_stake", 0) == 0:
            continue
        
        # Calculate aggregated metrics
        aggregated_data = aggregate_subnet_data(doc)
            
        formatted_doc = {
            "id": doc.get("id"),
            "hotkey": doc.get("hotkey"),
            "coldkey": doc.get("coldkey", ""),
            "take": doc.get("take", "0.0"),
            "verified": doc.get("verified", False),
            "name": doc.get("name", f"Validator {doc.get('hotkey', '')[:8]}"),
            "logo": doc.get("logo"),
            "url": doc.get("url"),
            "description": doc.get("description", "Validator on Bittensor network"),
            "verifiedBadge": doc.get("verifiedBadge", False),
            "twitter": doc.get("twitter"),
            "total_stake": doc.get("total_stake", 0),
            "last_updated": doc.get("last_updated"),
            
            # Add aggregated metrics as top-level fields
            "latestStake": aggregated_data["latestStake"],
            "stake1hAgo": aggregated_data["stake1hAgo"],
            "stake24hAgo": aggregated_data["stake24hAgo"],
            "stake7dAgo": aggregated_data["stake7dAgo"],
            "stake30dAgo": aggregated_data["stake30dAgo"],
            "hourlyYield": aggregated_data["hourlyYield"],
            "dailyYield": aggregated_data["dailyYield"],
            "weeklyYield": aggregated_data["weeklyYield"],
            "monthlyYield": aggregated_data["monthlyYield"],
            "hourlyApy": aggregated_data["hourlyApy"],
            "dailyApy": aggregated_data["dailyApy"],
            "weeklyApy": aggregated_data["weeklyApy"],
            "monthlyApy": aggregated_data["monthlyApy"],

            # Subnets
            "subnetsData": doc.get("subnetsData", {})
        }
        formatted_docs.append(formatted_doc)
    
    # Add pagination metadata
    result = {
        "data": formatted_docs,
        "pagination": {
            "total": total_count,
            "batch_size": batch_size if batch is not None else None,
            "current_batch": batch if batch is not None else None,
            "total_batches": (total_count + batch_size - 1) // batch_size if batch is not None else None
        }
    }
    
    return result

@app.get("/api/subnets")
def get_subnets():
    """Get all subnets with their names and symbols."""
    # Sample subnet data if not in DB yet
    default_subnets = {
        "0": {"name": "Foundational Subnet", "symbol": "ROOT"},
        "1": {"name": "Machine Learning Subnet", "symbol": "ML"},
        "2": {"name": "Text Prompting Subnet", "symbol": "TXT"},
        "3": {"name": "Miner Subnet", "symbol": "MINE"},
        "4": {"name": "Voice Subnet", "symbol": "VOICE"}
    }
    
    # Try to get from DB, fall back to defaults
    subnet_docs = list(subnets_collection.find({}, {"_id": 0}))
    
    if not subnet_docs:
        # If DB is empty, use defaults and potentially store them
        for subnet_id, subnet_data in default_subnets.items():
            subnets_collection.update_one(
                {"netuid": subnet_id},
                {"$set": {
                    "netuid": subnet_id,
                    "name": subnet_data["name"],
                    "symbol": subnet_data["symbol"],
                    "last_updated": datetime.now().isoformat()
                }},
                upsert=True
            )
        subnet_docs = list(subnets_collection.find({}, {"_id": 0}))
    
    return subnet_docs

@app.get("/api/validators/{hotkey}")
def get_validator_by_hotkey(hotkey: str):
    """Get a validator by its hotkey."""
    # Récupère un validateur spécifique par sa hotkey
    doc = validators_collection.find_one({"hotkey": hotkey}, {"_id": 0})
    
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Validator not found"})
    
    # Calculer le stake total
    doc["total_stake"] = calculate_total_stake(doc)
    
    # Calculate aggregated metrics and add them to the response
    aggregated_data = aggregate_subnet_data(doc)
    
    for key, value in aggregated_data.items():
        if value is not None:
            doc[key] = value
    
    return doc

@app.get("/api/validators/subnet/{subnet_id}")
def get_validators_by_subnet(
    subnet_id: int,
    sort_order: str = "desc",
    limit: Optional[int] = None,
    batch: Optional[int] = None,
    batch_size: int = 32
):
    """Get validators active in a specific subnet."""
    # Récupère tous les documents sans le champ "_id"
    docs = list(validators_collection.find({}, {"_id": 0}))
    
    # Filter validators who have stake in this subnet and add subnet_stake for sorting
    subnet_validators = []
    for doc in docs:
        subnet_stake = get_subnet_stake(doc, subnet_id)
        if subnet_stake > 0:
            doc["subnet_stake"] = subnet_stake
            subnet_validators.append(doc)
    
    # Get total count before pagination
    total_count = len(subnet_validators)
    
    # Sort by stake in this subnet
    subnet_validators.sort(key=lambda x: x.get("subnet_stake", 0), 
                          reverse=(sort_order.lower() == "desc"))
    
    # Apply batching if specified
    if batch is not None and isinstance(batch, int) and batch >= 0:
        start_idx = batch * batch_size
        end_idx = start_idx + batch_size
        subnet_validators = subnet_validators[start_idx:end_idx]
    # Otherwise apply limit if specified
    elif limit is not None and isinstance(limit, int) and limit > 0:
        subnet_validators = subnet_validators[:limit]
    
    formatted_docs = []
    for doc in subnet_validators:
        # Calculate aggregated metrics
        aggregated_data = aggregate_subnet_data(doc)
        
        formatted_doc = {
            "id": doc.get("id"),
            "hotkey": doc.get("hotkey"),
            "coldkey": doc.get("coldkey", ""),
            "take": doc.get("take", "0.0"),
            "verified": doc.get("verified", False),
            "name": doc.get("name", f"Validator {doc.get('hotkey', '')[:8]}"),
            "logo": doc.get("logo"),
            "url": doc.get("url"),
            "description": doc.get("description", "Validator on Bittensor network"),
            "verifiedBadge": doc.get("verifiedBadge", False),
            "twitter": doc.get("twitter"),
            "subnet_stake": doc.get("subnet_stake", 0),
            "last_updated": doc.get("last_updated"),
            
            # Add aggregated metrics
            "latestStake": aggregated_data["latestStake"],
            "stake1hAgo": aggregated_data["stake1hAgo"],
            "stake24hAgo": aggregated_data["stake24hAgo"],
            "stake7dAgo": aggregated_data["stake7dAgo"],
            "stake30dAgo": aggregated_data["stake30dAgo"],
            "hourlyYield": aggregated_data["hourlyYield"],
            "dailyYield": aggregated_data["dailyYield"],
            "weeklyYield": aggregated_data["weeklyYield"],
            "monthlyYield": aggregated_data["monthlyYield"],
            "hourlyApy": aggregated_data["hourlyApy"],
            "dailyApy": aggregated_data["dailyApy"],
            "weeklyApy": aggregated_data["weeklyApy"],
            "monthlyApy": aggregated_data["monthlyApy"],
            
            # Include only the relevant subnet data
            "subnet_data": doc.get("subnetsData", {}).get(str(subnet_id), {}),
            
            # Include the full subnetsData
            "subnetsData": doc.get("subnetsData", {})
        }
        formatted_docs.append(formatted_doc)
    
    # Add pagination metadata
    result = {
        "data": formatted_docs,
        "pagination": {
            "total": total_count,
            "batch_size": batch_size if batch is not None else None,
            "current_batch": batch if batch is not None else None,
            "total_batches": (total_count + batch_size - 1) // batch_size if batch is not None else None
        }
    }
    
    return result

# --- TRPC-COMPATIBLE BATCH ENDPOINT ---

@app.api_route("/api/trpc/{procedures}", methods=["GET", "POST"])
async def trpc_batch_endpoint(
    procedures: str, 
    request: Request,
    batch: Optional[int] = None,
    batch_size: int = 32
):
    procedure_list = procedures.split(',')

    if request.method == "GET":
        input_raw = request.query_params.get("input", "{}")
        try:
            input_data = json.loads(input_raw)
        except json.JSONDecodeError:
            input_data = {}
    else:
        body_bytes = await request.body()
        try:
            input_data = json.loads(body_bytes.decode())
        except Exception:
            input_data = {}

    metadata_path = os.path.join("data", "validator_metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            validator_metadata = json.load(f)
    else:
        validator_metadata = {}

    response_data = []

    for i, proc in enumerate(procedure_list):
        if proc == "delegates.getDelegates4":
            from main import get_validators
            result = get_validators(
                sort_by="total_stake",
                sort_order="desc",
                batch=batch,
                batch_size=batch_size
            )

            for idx, item in enumerate(result["data"]):
                meta = validator_metadata.get(item["hotkey"], {})
                for key in ["id", "name", "logo", "url", "description", "twitter", "verified", "verifiedBadge"]:
                    if key in meta:
                        item[key] = meta[key]
                item.setdefault("id", idx)

                # Remove empty subnets
                item["subnetsData"] = {k: v for k, v in item.get("subnetsData", {}).items() if v}

            response_data.append({
                "result": {
                    "data": {
                        "json": result["data"]
                    }
                }
            })

        elif proc == "subnets.getSubnetsNameAndSymbol":
            from main import get_subnets
            result = get_subnets()
            response_data.append({
                "result": {
                    "data": {
                        "json": result
                    }
                }
            })
        else:
            response_data.append({
                "error": {
                    "message": f"Unknown procedure: {proc}"
                }
            })

    return response_data
# --- HELPER ENDPOINT TO UPDATE SUBNET METADATA ---

@app.post("/api/admin/update-subnet")
def update_subnet_metadata(
    netuid: int, 
    name: str, 
    symbol: str,
    admin_key: str = Query(..., description="Admin key for authentication")
):
    """Admin endpoint to update subnet metadata."""
    # Simple authentication
    if admin_key != os.getenv("ADMIN_KEY", "your_secure_admin_key"):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    
    subnets_collection.update_one(
        {"netuid": str(netuid)},
        {"$set": {
            "netuid": str(netuid),
            "name": name,
            "symbol": symbol,
            "last_updated": datetime.now().isoformat()
        }},
        upsert=True
    )
    
    return {"success": True, "message": f"Updated metadata for subnet {netuid}"}

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# --- LANCEMENT ---

def start_api():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    threading.Thread(target=run_metadata_updater, daemon=True).start()
    threading.Thread(target=run_apy_updater, daemon=True).start()
    start_api()