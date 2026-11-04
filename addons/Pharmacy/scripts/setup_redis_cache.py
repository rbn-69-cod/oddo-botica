#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup Redis caching for pharmacy system

This script configures Redis for caching frequently accessed data.
"""

import subprocess
import sys


def check_redis_installed():
    """Check if Redis is installed"""
    try:
        result = subprocess.run(['redis-cli', 'ping'], 
                              capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def install_redis():
    """Install Redis server"""
    print("Installing Redis server...")
    subprocess.run(['sudo', 'apt-get', 'update'], check=True)
    subprocess.run(['sudo', 'apt-get', 'install', '-y', 'redis-server'], 
                  check=True)
    print("Redis installed successfully")


def start_redis():
    """Start Redis server"""
    print("Starting Redis server...")
    subprocess.run(['sudo', 'systemctl', 'start', 'redis'], check=True)
    subprocess.run(['sudo', 'systemctl', 'enable', 'redis'], check=True)
    print("Redis started successfully")


def configure_redis():
    """Configure Redis for optimal performance"""
    print("Configuring Redis...")
    
    # Backup original config
    subprocess.run(['sudo', 'cp', '/etc/redis/redis.conf', 
                   '/etc/redis/redis.conf.backup'], check=True)
    
    # Configure max memory (1GB)
    subprocess.run(['sudo', 'sed', '-i', 's/^# maxmemory .*/maxmemory 1gb/',
                   '/etc/redis/redis.conf'], check=True)
    
    # Configure eviction policy (allkeys-lru)
    subprocess.run(['sudo', 'sed', '-i', 's/^# maxmemory-policy .*/maxmemory-policy allkeys-lru/',
                   '/etc/redis/redis.conf'], check=True)
    
    # Restart Redis to apply config
    subprocess.run(['sudo', 'systemctl', 'restart', 'redis'], check=True)
    
    print("Redis configured successfully")


def install_python_redis():
    """Install Python Redis client"""
    print("Installing Python Redis client...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'redis'], 
                  check=True)
    print("Python Redis client installed successfully")


def test_redis():
    """Test Redis connection"""
    print("Testing Redis connection...")
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("Redis connection test successful")
        return True
    except Exception as e:
        print(f"Redis connection test failed: {e}")
        return False


def main():
    """Main setup function"""
    print("=== Redis Cache Setup for Pharmacy System ===\n")
    
    # Check if Redis is installed
    if not check_redis_installed():
        print("Redis is not installed. Installing...")
        install_redis()
    else:
        print("Redis is already installed.")
    
    # Start Redis
    start_redis()
    
    # Configure Redis
    configure_redis()
    
    # Install Python Redis client
    install_python_redis()
    
    # Test Redis
    if test_redis():
        print("\n=== Redis setup completed successfully ===")
        print("Redis is now ready for caching.")
        print("Add 'redis' to requirements.txt if not already present.")
    else:
        print("\n=== Redis setup failed ===")
        sys.exit(1)


if __name__ == '__main__':
    main()
