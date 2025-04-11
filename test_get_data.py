import asyncio
import json
import time
from datetime import datetime, timedelta
from bittensor import AsyncSubtensor
from rich.console import Console
from rich.table import Table

console = Console()
HOTKEY = "5F2CsUDVbRbVMXTh9fAzF9GacjVX7UapvRxidrxe7z8BYckQ"
NODE_URL = "wss://archive.chain.opentensor.ai:443"

# Time periods for stake calculations
TIME_PERIODS = {
    "1h": 60 * 60,        # 1 hour in seconds
    "24h": 24 * 60 * 60,  # 24 hours in seconds
    "7d": 7 * 24 * 60 * 60,  # 7 days in seconds
    "30d": 30 * 24 * 60 * 60,  # 30 days in seconds
}

async def get_block_for_timestamp(subtensor, target_timestamp):
    """Get the closest block number for a given timestamp."""
    current_block = await asyncio.wait_for(subtensor.block, timeout=30)
    current_timestamp = int(time.time())
    
    # Estimate blocks per second (Bittensor produces roughly 1 block every 12 seconds)
    blocks_per_second = 1 / 12
    
    # Calculate the approximate block number
    time_diff = current_timestamp - target_timestamp
    block_diff = int(time_diff * blocks_per_second)
    
    return max(1, current_block - block_diff)

async def get_stake(subtensor, hotkey, netuid, block):
    """Get stake for a specific hotkey on a subnet at a given block."""
    try:
        # Get all neurons and filter by hotkey
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

def format_stake(stake_value):
    """Format stake value for display."""
    if stake_value is None:
        return "N/A"
    
    if stake_value >= 1e18:  # If stake is very large (over 1 tao)
        return f"{stake_value/1e18:.4f} tao"
    else:
        return f"{stake_value} rao"

async def main():
    console.print("[bold blue]Starting Bittensor APY Calculator...[/bold blue]")
    
    try:
        async with AsyncSubtensor(NODE_URL) as subtensor:
            console.print("[green]Connected to Bittensor node[/green]")
            
            # Get current block and timestamp
            current_block = await asyncio.wait_for(subtensor.block, timeout=30)
            current_timestamp = int(time.time())
            console.print(f"📦 Current block: {current_block} ({datetime.fromtimestamp(current_timestamp)})")
            
            # Get historical blocks
            console.print("[bold blue]Calculating historical blocks...[/bold blue]")
            historical_blocks = {}
            for period, seconds in TIME_PERIODS.items():
                historical_timestamp = current_timestamp - seconds
                historical_blocks[period] = await get_block_for_timestamp(subtensor, historical_timestamp)
                console.print(f"📅 Block {period} ago: {historical_blocks[period]} ({datetime.fromtimestamp(historical_timestamp)})")
            
            # Get subnet list with timeout
            console.print("[bold blue]Retrieving subnet list...[/bold blue]")
            subnets = await asyncio.wait_for(subtensor.get_subnets(), timeout=30)
            console.print(f"Found {len(subnets)} subnets")
            
            # Process subnets of interest
            # Modify this list to include the subnets you're interested in
            target_subnets = list(range(10))  # Process subnets 0-9
            console.print(f"Processing subnets: {target_subnets}")
            
            # Create a table for display
            table = Table(title="Bittensor APY Calculator")
            table.add_column("Subnet", justify="right")
            table.add_column("Latest Stake", justify="right")
            table.add_column("1h Ago", justify="right")
            table.add_column("24h Ago", justify="right")
            table.add_column("7d Ago", justify="right")
            table.add_column("30d Ago", justify="right")
            table.add_column("Hourly APY", justify="right")
            table.add_column("Daily APY", justify="right")
            table.add_column("Weekly APY", justify="right")
            table.add_column("Monthly APY", justify="right")
            
            results = {}
            active_subnets = []
            
            for netuid in target_subnets:
                if netuid not in subnets:
                    console.print(f"[yellow]Subnet {netuid} not in subnet list, skipping...[/yellow]")
                    continue
                    
                console.print(f"\n[bold]Processing subnet {netuid}...[/bold]")
                
                # Get current stake
                console.print(f"Getting current stake for subnet {netuid}...")
                current_stake = await get_stake(subtensor, HOTKEY, netuid, current_block)
                
                if current_stake and current_stake > 0:
                    console.print(f"[green]✅ Active stake found for subnet {netuid}: {current_stake}[/green]")
                    active_subnets.append(netuid)
                    
                    # Initialize data structure for this subnet
                    subnet_data = {
                        "latestStake": str(current_stake),
                    }
                    
                    # Get historical stakes
                    historical_stakes = {}
                    for period, historical_block in historical_blocks.items():
                        console.print(f"Getting {period} ago stake for subnet {netuid} (block {historical_block})...")
                        historical_stake = await get_stake(subtensor, HOTKEY, netuid, historical_block)
                        stake_key = f"stake{period}Ago"
                        historical_stakes[period] = historical_stake
                        subnet_data[stake_key] = str(historical_stake) if historical_stake else None
                        
                        # Display the historical stake value explicitly
                        if historical_stake:
                            console.print(f"[green]Stake {period} ago: {historical_stake} ({format_stake(historical_stake)})[/green]")
                        else:
                            console.print(f"[yellow]No stake data available for {period} ago[/yellow]")
                    
                    # Calculate yields and APYs
                    time_periods = {
                        "1h": {"key": "hourlyYield", "apy_key": "hourlyApy"},
                        "24h": {"key": "dailyYield", "apy_key": "dailyApy"},
                        "7d": {"key": "weeklyYield", "apy_key": "weeklyApy"},
                        "30d": {"key": "monthlyYield", "apy_key": "monthlyApy"}
                    }
                    
                    for period, info in time_periods.items():
                        historical_stake = historical_stakes.get(period)
                        
                        if historical_stake:
                            # Calculate yield
                            yield_amount = max(0, current_stake - historical_stake)
                            subnet_data[info["key"]] = str(yield_amount)
                            console.print(f"{period} yield: {yield_amount} ({format_stake(yield_amount)})")
                            
                            # Calculate relative yield percentage for the period
                            if historical_stake > 0:
                                relative_yield_pct = (yield_amount / historical_stake) * 100
                                console.print(f"{period} relative yield: {relative_yield_pct:.2f}%")
                            
                            # Calculate APY
                            apy = await calculate_apy(
                                current_stake,
                                historical_stake,
                                TIME_PERIODS[period]
                            )
                            
                            if apy is not None:
                                subnet_data[info["apy_key"]] = f"{apy:.2f}"
                                console.print(f"{period} APY: {apy:.2f}%")
                            else:
                                subnet_data[info["apy_key"]] = None
                        else:
                            subnet_data[info["key"]] = None
                            subnet_data[info["apy_key"]] = None
                    
                    results[str(netuid)] = subnet_data
                    
                    # Add to table
                    table.add_row(
                        str(netuid),
                        format_stake(current_stake),
                        format_stake(historical_stakes.get("1h")),
                        format_stake(historical_stakes.get("24h")),
                        format_stake(historical_stakes.get("7d")),
                        format_stake(historical_stakes.get("30d")),
                        f"{subnet_data.get('hourlyApy', 'N/A')}%",
                        f"{subnet_data.get('dailyApy', 'N/A')}%",
                        f"{subnet_data.get('weeklyApy', 'N/A')}%",
                        f"{subnet_data.get('monthlyApy', 'N/A')}%"
                    )
            
            # Print table
            console.print(table)
            
            console.print(f"\n📊 Active subnets for hotkey {HOTKEY[:8]}: {active_subnets}")
            
            # Save results to JSON file
            with open("stake_apy_results.json", "w") as f:
                json.dump(results, f, indent=2)
            
            console.print(f"\n📊 Results saved to stake_apy_results.json")
    
    except asyncio.TimeoutError:
        console.print("[red]Operation timed out[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

if __name__ == "__main__":
    asyncio.run(main())