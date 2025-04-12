#!/usr/bin/env python3
"""
Cache utility functions for the Bittensor API.
"""

import os
import json
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cache")

# Default paths
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
VALIDATOR_METADATA_PATH = os.path.join(DEFAULT_DATA_DIR, "validator_metadata.json")
SUBNET_DATA_PATH = os.path.join(DEFAULT_DATA_DIR, "subnet_data.json")
VALIDATOR_DATA_PATH = os.path.join(DEFAULT_DATA_DIR, "validator_data.json")

class DataCache:
    """Cache for Bittensor data"""
    
    def __init__(self, 
                 validator_metadata_path=VALIDATOR_METADATA_PATH, 
                 subnet_data_path=SUBNET_DATA_PATH, 
                 validator_data_path=VALIDATOR_DATA_PATH):
        """Initialize the cache"""
        self.validator_metadata_path = validator_metadata_path
        self.subnet_data_path = subnet_data_path
        self.validator_data_path = validator_data_path
        
        # Make sure data directory exists
        os.makedirs(os.path.dirname(validator_metadata_path), exist_ok=True)
        
        # Cache data
        self.validator_metadata = {}
        self.subnet_data = {}
        self.validator_data = {}
        
        # Cache update times
        self.validator_metadata_updated = None
        self.subnet_data_updated = None
        self.validator_data_updated = None
        
        # Load cache from disk
        self.load_cache()
        
        # Lock for thread safety
        self.lock = threading.Lock()
    
    def load_cache(self):
        """Load cache from disk"""
        # Load validator metadata
        if os.path.exists(self.validator_metadata_path):
            try:
                with open(self.validator_metadata_path, 'r') as f:
                    self.validator_metadata = json.load(f)
                logger.info(f"Loaded validator metadata for {len(self.validator_metadata)} validators")
            except Exception as e:
                logger.error(f"Error loading validator metadata: {str(e)}")
                self.validator_metadata = {}
        
        # Load subnet data
        if os.path.exists(self.subnet_data_path):
            try:
                with open(self.subnet_data_path, 'r') as f:
                    self.subnet_data = json.load(f)
                logger.info(f"Loaded data for {len(self.subnet_data)} subnets")
            except Exception as e:
                logger.error(f"Error loading subnet data: {str(e)}")
                self.subnet_data = {}
        
        # Load validator data
        if os.path.exists(self.validator_data_path):
            try:
                with open(self.validator_data_path, 'r') as f:
                    self.validator_data = json.load(f)
                logger.info(f"Loaded data for {len(self.validator_data)} validators")
            except Exception as e:
                logger.error(f"Error loading validator data: {str(e)}")
                self.validator_data = {}
    
    def save_validator_metadata(self):
        """Save validator metadata to disk"""
        with self.lock:
            try:
                # Create backup first
                if os.path.exists(self.validator_metadata_path):
                    backup_path = f"{self.validator_metadata_path}.bak"
                    os.rename(self.validator_metadata_path, backup_path)
                
                # Save new data
                with open(self.validator_metadata_path, 'w') as f:
                    json.dump(self.validator_metadata, f, indent=2)
                
                self.validator_metadata_updated = datetime.now()
                logger.info(f"Saved metadata for {len(self.validator_metadata)} validators")
                return True
            except Exception as e:
                logger.error(f"Error saving validator metadata: {str(e)}")
                return False
    
    def save_subnet_data(self):
        """Save subnet data to disk"""
        with self.lock:
            try:
                # Create backup first
                if os.path.exists(self.subnet_data_path):
                    backup_path = f"{self.subnet_data_path}.bak"
                    os.rename(self.subnet_data_path, backup_path)
                
                # Save new data
                with open(self.subnet_data_path, 'w') as f:
                    json.dump(self.subnet_data, f, indent=2)
                
                self.subnet_data_updated = datetime.now()
                logger.info(f"Saved data for {len(self.subnet_data)} subnets")
                return True
            except Exception as e:
                logger.error(f"Error saving subnet data: {str(e)}")
                return False
    
    def save_validator_data(self):
        """Save validator data to disk"""
        with self.lock:
            try:
                # Create backup first
                if os.path.exists(self.validator_data_path):
                    backup_path = f"{self.validator_data_path}.bak"
                    os.rename(self.validator_data_path, backup_path)
                
                # Save new data
                with open(self.validator_data_path, 'w') as f:
                    json.dump(self.validator_data, f, indent=2)
                
                self.validator_data_updated = datetime.now()
                logger.info(f"Saved data for {len(self.validator_data)} validators")
                return True
            except Exception as e:
                logger.error(f"Error saving validator data: {str(e)}")
                return False
    
    def update_validator_metadata(self, metadata: Dict[str, Any]) -> bool:
        """Update validator metadata"""
        with self.lock:
            self.validator_metadata.update(metadata)
            return self.save_validator_metadata()
    
    def update_subnet_data(self, data: Dict[str, Any]) -> bool:
        """Update subnet data"""
        with self.lock:
            self.subnet_data = data
            return self.save_subnet_data()
    
    def update_validator_data(self, data: Dict[str, Any]) -> bool:
        """Update validator data"""
        with self.lock:
            self.validator_data = data
            return self.save_validator_data()
    
    def get_validator_metadata(self, hotkey: str = None) -> Dict[str, Any]:
        """Get validator metadata"""
        with self.lock:
            if hotkey:
                return self.validator_metadata.get(hotkey, {})
            return self.validator_metadata
    
    def get_subnet_data(self) -> Dict[str, Any]:
        """Get subnet data"""
        with self.lock:
            return self.subnet_data
    
    def get_validator_data(self, hotkey: str = None) -> Dict[str, Any]:
        """Get validator data"""
        with self.lock:
            if hotkey:
                return self.validator_data.get(hotkey, {})
            return self.validator_data
    
    def is_validator_metadata_stale(self, max_age_seconds: int = 3600) -> bool:
        """Check if validator metadata is stale"""
        if not self.validator_metadata_updated:
            return True
        
        age = (datetime.now() - self.validator_metadata_updated).total_seconds()
        return age > max_age_seconds
    
    def is_subnet_data_stale(self, max_age_seconds: int = 3600) -> bool:
        """Check if subnet data is stale"""
        if not self.subnet_data_updated:
            return True
        
        age = (datetime.now() - self.subnet_data_updated).total_seconds()
        return age > max_age_seconds
    
    def is_validator_data_stale(self, max_age_seconds: int = 3600) -> bool:
        """Check if validator data is stale"""
        if not self.validator_data_updated:
            return True
        
        age = (datetime.now() - self.validator_data_updated).total_seconds()
        return age > max_age_seconds

# Create global cache instance
cache = DataCache()

def get_cache() -> DataCache:
    """Get the cache instance"""
    return cache