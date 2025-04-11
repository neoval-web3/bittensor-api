import sys
import os
import json
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath("tao_apy_calculator/src"))

from utils.env import parse_env_data
from bittensor import AsyncSubtensor

from rich.progress import Progress, TimeElapsedColumn, SpinnerColumn
from rich.console import Console

from pymongo import MongoClient

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

console = Console()

VALIDATOR_METADATA_PATH = "data/validator_metadata.json"

# Constants for APY calculations
BLOCKS_PER_HOUR = 300  # Approximately 12 seconds per block
TIME_PERIODS = {
    "1h": 60 * 60,        # 1 hour in seconds
    "24h": 24 * 60 * 60,  # 24 hours in seconds
    "7d": 7 * 24 * 60 * 60,  # 7 days in seconds
    "30d": 30 * 24 * 60 * 60,  # 30 days in seconds
}

# --- UTILS ---
def load_json(path):
    if not os.path.exists(path) or os.stat(path).st_size == 0:
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        console.print(f"⚠️ Warning: Could not decode JSON from {path}, initializing empty data.", style="yellow")
        return {}

async def get_block_for_timestamp(subtensor, target_timestamp):
    """Get the closest block number for a given timestamp."""
    try:
        current_block = await asyncio.wait_for(subtensor.block, timeout=30)
        current_timestamp = int(time.time())
        
        # Estimate blocks per second (Bittensor produces roughly 1 block every 12 seconds)
        blocks_per_second = 1 / 12
        
        # Calculate the approximate block number
        time_diff = current_timestamp - target_timestamp
        block_diff = int(time_diff * blocks_per_second)
        
        return max(1, current_block - block_diff)
    except Exception as e:
        console.print(f"[red]Error calculating historical block: {e}")
        return None

async def get_stake(subtensor, hotkey, netuid, block):
    """Get stake for a specific hotkey on a subnet at a given block."""
    try:
        # Get all neurons and filter by hotkey (with timeout)
        neurons = await asyncio.wait_for(
            subtensor.neurons(netuid, block=block),
            timeout=30  # 30 second timeout
        )
        
        for neuron in neurons:
            if hasattr(neuron, 'hotkey') and neuron.hotkey == hotkey:
                if neuron.stake:
                    return int(getattr(neuron.stake, "rao", neuron.stake))
        return None
    except asyncio.TimeoutError:
        console.print(f"[yellow]Timeout retrieving neurons for subnet {netuid} at block {block}[/yellow]")
        return None
    except Exception as e:
        console.print(f"[red]Error getting stake for subnet {netuid} at block {block}: {e}[/red]")
        return None

async def calculate_apy(current_stake, past_stake, time_period_seconds):
    """Calculate APY based on current and past stake."""
    if not current_stake or not past_stake or past_stake == 0:
        return None
    
    # Calculate yield
    yield_amount = max(0, current_stake - past_stake)
    
    # Convert time period to days
    time_period_days = time_period_seconds / (24 * 60 * 60)
    
    # Calculate annualized yield
    annual_yield = yield_amount * (365 / time_period_days)
    
    # Calculate APY
    apy = (annual_yield / past_stake) * 100
    
    return apy

async def get_historical_stakes(subtensor, hotkey, netuid, current_block):
    """Get historical stakes for a validator on a specific subnet."""
    try:
        console.log(f"🔎 Checking current stake for {hotkey[:8]} on subnet {netuid}")
        
        # Get current stake
        current_stake = await get_stake(subtensor, hotkey, netuid, current_block)
        if not current_stake:
            console.log(f"⛔ No current stake found for {hotkey[:8]} on subnet {netuid}")
            return None, None, None, None, None, None
        
        # Get last stake (previous block)
        last_block = max(1, current_block - 5)  # Get stake from 5 blocks ago as "last stake"
        last_stake = await get_stake(subtensor, hotkey, netuid, last_block)
        console.log(f"📊 Last stake (5 blocks ago): {last_stake if last_stake else 'None'}")
            
        # Get historical timestamp blocks
        current_timestamp = int(time.time())
        historical_blocks = {}
        for period, seconds in TIME_PERIODS.items():
            historical_timestamp = current_timestamp - seconds
            historical_blocks[period] = await get_block_for_timestamp(subtensor, historical_timestamp)
            console.log(f"📅 Block {period} ago: {historical_blocks[period]}")
        
        # Get historical stakes
        stake_1h_ago = await get_stake(subtensor, hotkey, netuid, historical_blocks["1h"])
        stake_24h_ago = await get_stake(subtensor, hotkey, netuid, historical_blocks["24h"])
        stake_7d_ago = await get_stake(subtensor, hotkey, netuid, historical_blocks["7d"])
        stake_30d_ago = await get_stake(subtensor, hotkey, netuid, historical_blocks["30d"])
        
        console.log(f"✅ Successfully retrieved historical stakes for {hotkey[:8]} on subnet {netuid}")
        return current_stake, last_stake, stake_1h_ago, stake_24h_ago, stake_7d_ago, stake_30d_ago
    except Exception as e:
        console.print(f"[red]Error getting historical stakes for {hotkey} on subnet {netuid}: {e}")
        return None, None, None, None, None, None

async def calculate_hotkey_subnet_apy(subtensor, hotkey, netuid, stakes):
    """Calculate APY metrics for a validator on a subnet."""
    try:
        current_stake, last_stake, stake_1h_ago, stake_24h_ago, stake_7d_ago, stake_30d_ago = stakes
        
        # Calculate yields
        hourly_yield = max(0, current_stake - (stake_1h_ago or current_stake))
        daily_yield = max(0, current_stake - (stake_24h_ago or current_stake))
        weekly_yield = max(0, current_stake - (stake_7d_ago or current_stake))
        monthly_yield = max(0, current_stake - (stake_30d_ago or current_stake))
        
        # Calculate APYs
        hourly_apy = await calculate_apy(current_stake, stake_1h_ago, TIME_PERIODS["1h"]) if stake_1h_ago else None
        daily_apy = await calculate_apy(current_stake, stake_24h_ago, TIME_PERIODS["24h"]) if stake_24h_ago else None
        weekly_apy = await calculate_apy(current_stake, stake_7d_ago, TIME_PERIODS["7d"]) if stake_7d_ago else None
        monthly_apy = await calculate_apy(current_stake, stake_30d_ago, TIME_PERIODS["30d"]) if stake_30d_ago else None
        
        return {
            "lastStake": last_stake,
            "hourlyYield": hourly_yield,
            "dailyYield": daily_yield,
            "weeklyYield": weekly_yield,
            "monthlyYield": monthly_yield,
            "hourlyApy": hourly_apy,
            "dailyApy": daily_apy,
            "weeklyApy": weekly_apy,
            "monthlyApy": monthly_apy
        }
    except Exception as e:
        console.print(f"[red]Error calculating APY for {hotkey} on subnet {netuid}: {e}")
        return {
            "lastStake": None,
            "hourlyYield": None,
            "dailyYield": None,
            "weeklyYield": None,
            "monthlyYield": None,
            "hourlyApy": None,
            "dailyApy": None,
            "weeklyApy": None,
            "monthlyApy": None
        }

async def process_subnet_for_validator(subtensor, hotkey, netuid, validator_metadata, block, timestamp):
    """Process a single subnet for a validator and store in MongoDB."""
    try:
        console.log(f"📥 Checking stake for {hotkey[:8]} on subnet {netuid}")
        
        # Get current and historical stakes
        stakes = await get_historical_stakes(subtensor, hotkey, netuid, block)
        if not stakes or stakes[0] is None:
            console.log(f"⚠️ No stake data for {hotkey[:8]} on subnet {netuid}")
            return False

        current_stake, last_stake, stake_1h_ago, stake_24h_ago, stake_7d_ago, stake_30d_ago = stakes
        
        if current_stake > 0:
            console.log(f"✅ Active stake found on subnet {netuid}: {current_stake}")
            
            # Calculate APY data
            console.log(f"📊 Calculating APY for {hotkey[:8]} on subnet {netuid}")
            apy_data = await calculate_hotkey_subnet_apy(subtensor, hotkey, netuid, stakes)
            
            # Create validator base data if it doesn't exist in MongoDB
            validator_base = {
                "id": validator_metadata.get("id", 0),
                "hotkey": hotkey,
                "coldkey": validator_metadata.get("coldkey", ""),
                "take": validator_metadata.get("take", "0.0"),
                "verified": validator_metadata.get("verified", False),
                "name": validator_metadata.get("name", f"Validator {hotkey[:8]}"),
                "logo": validator_metadata.get("logo"),
                "url": validator_metadata.get("url"),
                "description": validator_metadata.get("description", "Validator on Bittensor network"),
                "verifiedBadge": validator_metadata.get("verifiedBadge", False),
                "twitter": validator_metadata.get("twitter"),
                "last_updated": timestamp
            }
            
            # Create or update base document for this validator if it doesn't exist
            validators_collection.update_one(
                {"hotkey": hotkey},
                {"$set": validator_base},
                upsert=True
            )
            console.log(f"✅ Updated validator base data for {hotkey} in MongoDB")
            
            # Prepare subnet data
            subnet_data = {
                "latestStake": str(current_stake),
                "lastStake": None if last_stake is None else str(last_stake),
                "stake1hAgo": None if stake_1h_ago is None else str(stake_1h_ago),
                "stake24hAgo": None if stake_24h_ago is None else str(stake_24h_ago),
                "stake7dAgo": None if stake_7d_ago is None else str(stake_7d_ago),
                "stake30dAgo": None if stake_30d_ago is None else str(stake_30d_ago),
                "hourlyYield": None if apy_data["hourlyYield"] is None else str(apy_data["hourlyYield"]),
                "dailyYield": None if apy_data["dailyYield"] is None else str(apy_data["dailyYield"]),
                "weeklyYield": None if apy_data["weeklyYield"] is None else str(apy_data["weeklyYield"]),
                "monthlyYield": None if apy_data["monthlyYield"] is None else str(apy_data["monthlyYield"]),
                "hourlyApy": None if apy_data["hourlyApy"] is None else f"{apy_data['hourlyApy']:.2f}",
                "dailyApy": None if apy_data["dailyApy"] is None else f"{apy_data['dailyApy']:.2f}",
                "weeklyApy": None if apy_data["weeklyApy"] is None else f"{apy_data['weeklyApy']:.2f}",
                "monthlyApy": None if apy_data["monthlyApy"] is None else f"{apy_data['monthlyApy']:.2f}"
            }
            
            # Update the subnet data in MongoDB
            validators_collection.update_one(
                {"hotkey": hotkey},
                {"$set": {
                    f"subnetsData.{netuid}": subnet_data,
                    str(netuid): subnet_data,  # For backward compatibility
                    "last_updated": timestamp
                }}
            )
            console.log(f"💾 Stored subnet {netuid} data for {hotkey} in MongoDB")
            return True
        else:
            console.log(f"⚠️ No active stake for {hotkey[:8]} on subnet {netuid}")
            return False
    except Exception as e:
        console.print(f"[red]Error processing subnet {netuid} for {hotkey}: {e}")
        return False

async def main():
    metadata = load_json(VALIDATOR_METADATA_PATH)
    if not metadata:
        console.print("❌ No validator metadata found. Please run metadata_sync.py first.", style="red")
        return

    timestamp = datetime.now().isoformat()
    [node_url, batch_size] = parse_env_data()

    console.print(f"🚀 Starting validator data collection with node URL: {node_url}", style="green")
    async with AsyncSubtensor(node_url) as subtensor:
        try:
            block = await asyncio.wait_for(subtensor.block, timeout=30)
            console.print(f"🟢 Connected to Bittensor at block {block}", style="green")
            console.print(f"🔍 Found {len(metadata)} validators in metadata", style="cyan")

            # Get subnet list with timeout
            console.print("[bold blue]Retrieving subnet list...[/bold blue]")
            subnets = await asyncio.wait_for(subtensor.get_subnets(), timeout=30)
            
            if isinstance(subnets, list):
                subnet_ids = [s.netuid if hasattr(s, 'netuid') else s for s in subnets]
            else:
                subnet_ids = list(range(100))  # Fallback to checking first 100 subnet IDs
                
            console.print(f"📡 Found {len(subnet_ids)} potential subnets")

            with Progress(SpinnerColumn(), *Progress.get_default_columns(), TimeElapsedColumn(), console=console) as progress:
                task = progress.add_task("[cyan]Processing validators...", total=len(metadata))
                count_validators_processed = 0
                count_active_subnets = 0

                for i, (hotkey, info) in enumerate(metadata.items(), 1):
                    progress.update(task, description=f"[cyan]Validator {i}/{len(metadata)}: {hotkey[:8]}")
                    try:
                        validator_has_active_subnet = False
                        
                        # Process each subnet for this validator
                        for netuid in subnet_ids:
                            subnet_processed = await process_subnet_for_validator(
                                subtensor, hotkey, netuid, info, block, timestamp
                            )
                            if subnet_processed:
                                validator_has_active_subnet = True
                                count_active_subnets += 1
                        
                        if validator_has_active_subnet:
                            count_validators_processed += 1
                            console.print(f"✅ Processed validator {hotkey[:8]} | {info.get('name', 'Unknown')}")
                        else:
                            console.print(f"⚠️ No active subnets for validator {hotkey[:8]}")
                            
                    except Exception as e:
                        console.print(f"❌ Error processing validator {hotkey}: {e}", style="red")
                    progress.update(task, advance=1)

            console.print(f"✅ Completed! Processed {count_validators_processed} validators with {count_active_subnets} active subnets.", style="green")
        except asyncio.TimeoutError:
            console.print("[red]Connection to Bittensor node timed out[/red]")
        except Exception as e:
            console.print(f"[red]Error in main process: {e}[/red]")

if __name__ == "__main__":
    asyncio.run(main())