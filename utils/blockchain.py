#!/usr/bin/env python3
"""
Blockchain utility functions for interacting with Bittensor network.
"""

import logging
import bittensor as bt
import numpy as np
from typing import List, Dict, Optional, Any, Union

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("blockchain")

# Subnet names mapping
SUBNET_NAMES = {
    0: "Text Prompting",
    1: "Image Generation",
    2: "Miner",
    3: "Code",
    4: "Audio Generation",
    5: "Video Generation",
    6: "Music Generation", 
    7: "File Storage",
    8: "Gaming",
    9: "Scientific Computing",
    10: "Defi",
    11: "Miscellaneous",
    12: "Oracle",
    13: "DNS"
}

class BittensorBlockchain:
    """Class for interacting with the Bittensor blockchain"""
    
    def __init__(self, network="finney"):
        """Initialize the blockchain connection"""
        self.network = network
        self.subtensor = None
        self.connect()
    
    def connect(self):
        """Connect to the Bittensor network"""
        try:
            # Direct initialization
            self.subtensor = bt.subtensor(network=self.network)
            logger.info(f"Connected to Bittensor {self.network} network")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize subtensor: {str(e)}")
            return False
    
    def is_connected(self):
        """Check if connected to the blockchain"""
        return self.subtensor is not None
    
    def reconnect(self):
        """Reconnect to the blockchain if disconnected"""
        if not self.is_connected():
            return self.connect()
        return True
    
    def get_subnet_netuids(self) -> List[int]:
        """Get all subnet netuids"""
        self.reconnect()
        
        # Hard-coded subnet list based on active Bittensor subnets
        # This is a fallback when API methods fail
        known_subnets = list(range(14))  # Subnets 0-13
        
        try:
            # Using the alternate method from debug output
            subnets = self.subtensor.get_subnets()
            if isinstance(subnets, list) and len(subnets) > 0:
                logger.info(f"Found {len(subnets)} subnets")
                return subnets
        except Exception as e:
            logger.warning(f"Error using get_subnets(): {str(e)}")
        
        # Fallback to metagraph approach
        try:
            verified_subnets = []
            for netuid in known_subnets:
                try:
                    # Check if subnet exists by trying to create a metagraph
                    metagraph = bt.metagraph(netuid=netuid, network=self.network)
                    # If metagraph creation succeeds and has neurons, subnet exists
                    if hasattr(metagraph, 'hotkeys') and len(metagraph.hotkeys) > 0:
                        logger.info(f"Verified subnet {netuid} with {len(metagraph.hotkeys)} neurons")
                        verified_subnets.append(netuid)
                except Exception as e:
                    pass  # Skip subnets that can't be loaded
            
            if verified_subnets:
                logger.info(f"Verified {len(verified_subnets)} active subnets via metagraph check")
                return verified_subnets
        except Exception as e:
            logger.warning(f"Error using metagraph approach: {str(e)}")
        
        # Fallback to known subnet list
        logger.warning("Could not verify subnets, using fallback list")
        return known_subnets
    
    def get_subnet_validators(self, netuid: int) -> List:
        """Get validators for a subnet"""
        self.reconnect()
        
        # Create a metagraph for this subnet
        try:
            metagraph = bt.metagraph(netuid=netuid, network=self.network)
            
            # Check if this is a validator metagraph with stake info
            if hasattr(metagraph, 'S') and len(metagraph.S) > 0 and hasattr(metagraph, 'hotkeys'):
                # Create validator objects from hotkeys with positive stake
                validators = []
                for i, stake in enumerate(metagraph.S):
                    if stake > 0 and i < len(metagraph.hotkeys):
                        # Create a simple validator object with hotkey
                        class Validator:
                            def __init__(self, hotkey):
                                self.hotkey = hotkey
                        
                        validators.append(Validator(metagraph.hotkeys[i]))
                
                logger.info(f"Found {len(validators)} validators for subnet {netuid} using metagraph")
                return validators
        except Exception as e:
            logger.error(f"Error getting validators for subnet {netuid}: {str(e)}")
        
        # Return empty list if all methods fail
        return []
    
    def get_validator_stake(self, netuid: int, hotkey: str) -> int:
        """Get validator stake in a subnet"""
        self.reconnect()
        
        try:
            # Convert hotkey to string if needed
            if not isinstance(hotkey, str):
                hotkey = str(hotkey)
            
            # Try to get stake using get_stake_for_hotkey
            return int(self.subtensor.get_stake_for_hotkey(hotkey))
        except Exception as e1:
            logger.debug(f"Error with get_stake_for_hotkey: {str(e1)}")
            
            # Try metagraph approach
            try:
                metagraph = bt.metagraph(netuid=netuid, network=self.network)
                uid = None
                
                # Find uid for this hotkey
                for i, mh in enumerate(metagraph.hotkeys):
                    if str(mh) == hotkey:
                        uid = i
                        break
                
                if uid is not None and uid < len(metagraph.S):
                    return int(metagraph.S[uid])
            except Exception as e2:
                logger.debug(f"Error getting stake via metagraph: {str(e2)}")
        
        # Return default value
        return 0
    
    def get_total_subnet_stake(self, netuid: int) -> int:
        """Get total stake in a subnet"""
        self.reconnect()
        
        try:
            # Try metagraph approach
            metagraph = bt.metagraph(netuid=netuid, network=self.network)
            if hasattr(metagraph, 'S'):
                return int(sum(metagraph.S))
        except Exception as e:
            logger.error(f"Error getting total stake for subnet {netuid}: {str(e)}")
        
        # Return default value
        return 0
    
    def get_subnet_hyperparameters(self, netuid: int) -> Any:
        """Get subnet hyperparameters"""
        self.reconnect()
        
        try:
            return self.subtensor.get_subnet_hyperparameters(netuid)
        except Exception as e:
            logger.error(f"Error getting hyperparameters for subnet {netuid}: {str(e)}")
            
        # Return fallback values similar to TaoYield
        class DummyHyperparams:
            def __init__(self):
                self.tempo = 99
                self.max_allowed_validators = 256
                self.min_allowed_weights = 1024
                self.max_weights_limit = 1024
        
        return DummyHyperparams()
    
    def get_current_block(self) -> int:
        """Get current block number"""
        self.reconnect()
        
        try:
            return self.subtensor.get_current_block()
        except Exception as e:
            logger.error(f"Error getting current block: {str(e)}")
            return 0
    
    def is_validator_in_subnet(self, netuid: int, hotkey: str) -> bool:
        """Check if validator is in subnet"""
        # Use stake check as proxy for validator status
        stake = self.get_validator_stake(netuid, hotkey)
        return stake > 0
    
    def get_validator_owner(self, netuid: int, hotkey: str) -> str:
        """Get validator owner (coldkey)"""
        self.reconnect()
        
        try:
            coldkey = self.subtensor.get_hotkey_owner(hotkey)
            return str(coldkey) if coldkey else f"Unknown-{hotkey[-8:]}"
        except Exception as e:
            logger.error(f"Error getting owner for validator {hotkey}: {str(e)}")
        
        return f"Unknown-{hotkey[-8:]}"

# Create a globally accessible instance
blockchain = BittensorBlockchain()

def get_blockchain() -> BittensorBlockchain:
    """Get the blockchain instance"""
    return blockchain