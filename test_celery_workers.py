"""
Test Celery Workers and Tasks

This script tests that Celery workers are running and can process tasks.
It submits test tasks and monitors their execution.

Usage:
    python test_celery_workers.py
"""

import sys
import time
from typing import Optional

from celery.result import AsyncResult

from src.workers.celery_app import celery_app
from src.workers.slack_sync_task import sync_slack_channel, sync_slack_workspace


def check_worker_status() -> bool:
    """
    Check if Celery workers are running.
    
    Returns:
        True if workers are active, False otherwise
    """
    print("\n🔍 Checking Celery worker status...")
    
    try:
        # Get active workers
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        
        if not active_workers:
            print("❌ No active workers found")
            print("\n   Start a worker with:")
            print("   ./scripts/start-worker.sh")
            return False
        
        print(f"✅ Found {len(active_workers)} active worker(s):")
        for worker_name in active_workers.keys():
            print(f"   - {worker_name}")
        
        # Get worker stats
        stats = inspect.stats()
        if stats:
            for worker_name, worker_stats in stats.items():
                pool = worker_stats.get("pool", {})
                print(f"\n   {worker_name}:")
                print(f"     Pool: {pool.get('implementation', 'unknown')}")
                print(f"     Max concurrency: {pool.get('max-concurrency', 'N/A')}")
        
        return True
    
    except Exception as e:
        print(f"❌ Error checking workers: {e}")
        return False


def check_broker_connection() -> bool:
    """
    Check if Celery can connect to the broker.
    
    Returns:
        True if connected, False otherwise
    """
    print("\n🔍 Checking broker connection...")
    
    try:
        # Try to get registered tasks
        registered_tasks = list(celery_app.tasks.keys())
        print(f"✅ Connected to broker")
        print(f"   Registered tasks: {len(registered_tasks)}")
        
        # Show some tasks
        task_list = [t for t in registered_tasks if not t.startswith('celery.')]
        if task_list:
            print(f"\n   Custom tasks:")
            for task in task_list[:10]:  # Show first 10
                print(f"     - {task}")
            if len(task_list) > 10:
                print(f"     ... and {len(task_list) - 10} more")
        
        return True
    
    except Exception as e:
        print(f"❌ Broker connection failed: {e}")
        print("\n   Make sure Redis is running:")
        print("   docker-compose up -d redis")
        return False


def submit_test_task() -> Optional[AsyncResult]:
    """
    Submit a simple test task.
    
    Returns:
        AsyncResult if task submitted, None otherwise
    """
    print("\n📤 Submitting test task...")
    
    try:
        # Use a simple Celery built-in task for testing
        from celery import group
        
        # Create a simple signature
        task = celery_app.signature('celery.ping')
        result = task.apply_async()
        
        print(f"✅ Task submitted: {result.id}")
        print(f"   Status: {result.status}")
        
        return result
    
    except Exception as e:
        print(f"❌ Failed to submit task: {e}")
        return None


def monitor_task(result: AsyncResult, timeout: int = 10) -> bool:
    """
    Monitor task execution.
    
    Args:
        result: AsyncResult to monitor
        timeout: Maximum wait time in seconds
        
    Returns:
        True if task succeeded, False otherwise
    """
    print(f"\n⏳ Monitoring task {result.id}...")
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        status = result.status
        print(f"   Status: {status}", end="\r")
        
        if status == "SUCCESS":
            print(f"\n✅ Task completed successfully")
            if result.result:
                print(f"   Result: {result.result}")
            return True
        
        elif status == "FAILURE":
            print(f"\n❌ Task failed")
            print(f"   Error: {result.result}")
            return False
        
        elif status in ["PENDING", "STARTED", "RETRY"]:
            time.sleep(0.5)
        
        else:
            print(f"\n⚠️  Unknown status: {status}")
            return False
    
    print(f"\n⏱️  Task timeout after {timeout}s (status: {result.status})")
    return False


def list_available_tasks():
    """List all available Celery tasks."""
    print("\n📋 Available Tasks:")
    print("="*80)
    
    registered_tasks = sorted(celery_app.tasks.keys())
    custom_tasks = [t for t in registered_tasks if not t.startswith('celery.')]
    
    if custom_tasks:
        print("\n🔧 Custom Tasks:")
        for task in custom_tasks:
            print(f"   - {task}")
    
    print(f"\n   Total registered tasks: {len(registered_tasks)}")
    print(f"   Custom tasks: {len(custom_tasks)}")


def run_diagnostics():
    """Run full diagnostic check."""
    print("\n" + "="*80)
    print("🏥 Celery Worker Diagnostics")
    print("="*80)
    
    # Check broker
    broker_ok = check_broker_connection()
    
    # Check workers
    workers_ok = check_worker_status()
    
    # List tasks
    list_available_tasks()
    
    # Try test task if workers are running
    if broker_ok and workers_ok:
        result = submit_test_task()
        if result:
            task_ok = monitor_task(result, timeout=10)
        else:
            task_ok = False
    else:
        task_ok = False
    
    # Summary
    print("\n" + "="*80)
    print("📊 Diagnostic Summary:")
    print("="*80)
    print(f"   Broker Connection: {'✅ OK' if broker_ok else '❌ FAILED'}")
    print(f"   Active Workers: {'✅ OK' if workers_ok else '❌ FAILED'}")
    print(f"   Task Execution: {'✅ OK' if task_ok else '❌ FAILED'}")
    
    overall = broker_ok and workers_ok and task_ok
    print(f"\n   Overall Status: {'✅ HEALTHY' if overall else '❌ UNHEALTHY'}")
    print("="*80 + "\n")
    
    return overall


def manual_test_slack_sync():
    """Manually test Slack sync task."""
    print("\n" + "="*80)
    print("🧪 Manual Slack Sync Test")
    print("="*80)
    
    # This requires connector_id=1 to exist and be a Slack connector
    connector_id = 1
    channel_id = "CGREG0X9A"  # #ideas channel
    
    print(f"\n📤 Submitting Slack sync task...")
    print(f"   Connector ID: {connector_id}")
    print(f"   Channel ID: {channel_id}")
    
    try:
        result = sync_slack_channel.apply_async(
            args=(connector_id, channel_id),
            countdown=0,
        )
        
        print(f"✅ Task submitted: {result.id}")
        
        # Monitor with longer timeout
        print(f"\n⏳ Waiting for task to complete (this may take a minute)...")
        
        start_time = time.time()
        timeout = 300  # 5 minutes
        
        while time.time() - start_time < timeout:
            status = result.status
            
            if status == "SUCCESS":
                stats = result.result
                print(f"\n✅ Sync completed successfully!")
                print(f"\n   Statistics:")
                for key, value in stats.items():
                    print(f"     {key}: {value}")
                return True
            
            elif status == "FAILURE":
                print(f"\n❌ Sync failed: {result.result}")
                return False
            
            elif status in ["PENDING", "STARTED", "RETRY"]:
                elapsed = int(time.time() - start_time)
                print(f"   Status: {status} (elapsed: {elapsed}s)", end="\r")
                time.sleep(2)
            
            else:
                print(f"\n⚠️  Unknown status: {status}")
                return False
        
        print(f"\n⏱️  Task timeout after {timeout}s")
        return False
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Celery workers")
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Run full diagnostics",
    )
    parser.add_argument(
        "--test-slack",
        action="store_true",
        help="Test Slack sync task",
    )
    
    args = parser.parse_args()
    
    if args.test_slack:
        success = manual_test_slack_sync()
        sys.exit(0 if success else 1)
    elif args.diagnostics or len(sys.argv) == 1:
        success = run_diagnostics()
        sys.exit(0 if success else 1)
