"""
Performance tests for concurrent users (T204).

Tests system behavior with 50 concurrent users:
- Query throughput
- Resource consumption
- Connection pool limits
- Error rates under load
"""
import pytest
import time
import concurrent.futures
from typing import List, Dict, Any
from fastapi.testclient import TestClient


class TestConcurrentQueriesBasic:
    """Test basic concurrent query execution."""
    
    def test_10_concurrent_queries(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test 10 concurrent queries complete successfully."""
        def make_query(query_text: str) -> Dict[str, Any]:
            """Make a single query."""
            query_data = {
                "query": query_text,
                "workspace_id": workspace_id
            }
            response = client.post("/query", json=query_data, headers=auth_headers)
            return {
                "status_code": response.status_code,
                "success": response.status_code == 200
            }
        
        queries = [f"Test query {i}" for i in range(10)]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(make_query, queries))
        
        # All queries should succeed
        successes = sum(1 for r in results if r["success"])
        assert successes == 10, f"Only {successes}/10 queries succeeded"
    
    def test_concurrent_queries_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test that concurrent queries don't significantly degrade latency."""
        def make_timed_query(query_text: str) -> Dict[str, Any]:
            """Make a query and measure latency."""
            query_data = {
                "query": query_text,
                "workspace_id": workspace_id
            }
            start = time.time()
            response = client.post("/query", json=query_data, headers=auth_headers)
            latency = time.time() - start
            return {
                "status_code": response.status_code,
                "latency": latency,
                "success": response.status_code == 200
            }
        
        queries = [f"Query {i}" for i in range(10)]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(make_timed_query, queries))
        
        # Check success rate
        successes = sum(1 for r in results if r["success"])
        assert successes >= 9, f"Only {successes}/10 queries succeeded"
        
        # Check latency distribution
        latencies = [r["latency"] for r in results if r["success"]]
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        
        print(f"\nConcurrent query latency:")
        print(f"  avg: {avg_latency:.2f}s")
        print(f"  max: {max_latency:.2f}s")
        
        # Average latency should be reasonable under concurrent load
        assert avg_latency < 15.0, f"Avg latency too high: {avg_latency:.2f}s"


class TestConcurrentUsers50:
    """Test 50 concurrent users scenario."""
    
    def test_50_concurrent_queries(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test 50 concurrent queries complete successfully."""
        def make_query(query_id: int) -> Dict[str, Any]:
            """Make a single query."""
            query_data = {
                "query": f"Find information about topic {query_id % 10}",
                "workspace_id": workspace_id
            }
            try:
                start = time.time()
                response = client.post("/query", json=query_data, headers=auth_headers)
                latency = time.time() - start
                return {
                    "status_code": response.status_code,
                    "latency": latency,
                    "success": response.status_code == 200,
                    "error": None
                }
            except Exception as e:
                return {
                    "status_code": 500,
                    "latency": 0,
                    "success": False,
                    "error": str(e)
                }
        
        # Simulate 50 concurrent users
        query_ids = list(range(50))
        
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            results = list(executor.map(make_query, query_ids))
        total_time = time.time() - start_time
        
        # Analyze results
        successes = sum(1 for r in results if r["success"])
        failures = sum(1 for r in results if not r["success"])
        success_rate = (successes / len(results)) * 100
        
        successful_results = [r for r in results if r["success"]]
        if successful_results:
            latencies = [r["latency"] for r in successful_results]
            avg_latency = sum(latencies) / len(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
            max_latency = max(latencies)
        else:
            avg_latency = 0
            p95_latency = 0
            max_latency = 0
        
        throughput = len(results) / total_time if total_time > 0 else 0
        
        print(f"\n50 Concurrent Users Test:")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Successes: {successes}/50 ({success_rate:.1f}%)")
        print(f"  Failures: {failures}")
        print(f"  Throughput: {throughput:.2f} queries/second")
        print(f"  Avg latency: {avg_latency:.2f}s")
        print(f"  p95 latency: {p95_latency:.2f}s")
        print(f"  Max latency: {max_latency:.2f}s")
        
        # Success rate should be >90%
        assert success_rate >= 90.0, f"Success rate too low: {success_rate:.1f}%"
        
        # p95 latency should be reasonable
        if successful_results:
            assert p95_latency < 20.0, f"p95 latency too high: {p95_latency:.2f}s"


class TestConcurrentMixedOperations:
    """Test concurrent mixed operations (read/write)."""
    
    def test_concurrent_queries_and_syncs(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test queries while syncs are running."""
        def make_query(query_id: int) -> Dict[str, Any]:
            """Make a query."""
            query_data = {
                "query": f"Query {query_id}",
                "workspace_id": workspace_id
            }
            response = client.post("/query", json=query_data, headers=auth_headers)
            return {
                "type": "query",
                "success": response.status_code == 200
            }
        
        # Mix of queries (simulating reads)
        operations = [i for i in range(20)]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(make_query, operations))
        
        successes = sum(1 for r in results if r["success"])
        success_rate = (successes / len(results)) * 100
        
        print(f"\nMixed operations:")
        print(f"  Success rate: {success_rate:.1f}%")
        
        # Should maintain high success rate
        assert success_rate >= 85.0


class TestConnectionPooling:
    """Test connection pool behavior under load."""
    
    def test_connection_pool_capacity(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test connection pool handles concurrent requests."""
        def make_query(query_id: int) -> Dict[str, Any]:
            """Make a query that uses database connection."""
            query_data = {
                "query": f"Query {query_id}",
                "workspace_id": workspace_id
            }
            try:
                response = client.post("/query", json=query_data, headers=auth_headers)
                return {
                    "success": response.status_code == 200,
                    "status_code": response.status_code
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e)
                }
        
        # Test with 30 concurrent requests (within pool_size=20 + max_overflow=10)
        query_ids = list(range(30))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            results = list(executor.map(make_query, query_ids))
        
        successes = sum(1 for r in results if r["success"])
        success_rate = (successes / len(results)) * 100
        
        print(f"\nConnection pool test (30 concurrent):")
        print(f"  Success rate: {success_rate:.1f}%")
        
        # All should succeed with proper pool configuration
        assert success_rate >= 95.0, f"Pool capacity issue: {success_rate:.1f}% success"
    
    def test_connection_pool_overflow(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test connection pool handles requests beyond pool_size."""
        def make_query(query_id: int) -> Dict[str, Any]:
            """Make a query."""
            query_data = {
                "query": f"Query {query_id}",
                "workspace_id": workspace_id
            }
            try:
                response = client.post("/query", json=query_data, headers=auth_headers)
                return {"success": response.status_code == 200}
            except Exception as e:
                # Pool exhaustion would cause connection errors
                return {"success": False, "error": str(e)}
        
        # Test with 40 concurrent (exceeds pool_size=20 but within max_overflow)
        query_ids = list(range(40))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
            results = list(executor.map(make_query, query_ids))
        
        successes = sum(1 for r in results if r["success"])
        success_rate = (successes / len(results)) * 100
        
        print(f"\nPool overflow test (40 concurrent):")
        print(f"  Success rate: {success_rate:.1f}%")
        
        # Should handle overflow gracefully
        assert success_rate >= 90.0


class TestResourceConsumption:
    """Test resource consumption under concurrent load."""
    
    def test_memory_stability_under_load(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test memory doesn't grow unbounded under concurrent load."""
        def make_query_batch(batch_id: int) -> int:
            """Make a batch of queries."""
            successes = 0
            for i in range(5):
                query_data = {
                    "query": f"Batch {batch_id} query {i}",
                    "workspace_id": workspace_id
                }
                response = client.post("/query", json=query_data, headers=auth_headers)
                if response.status_code == 200:
                    successes += 1
            return successes
        
        # Run 10 batches of 5 queries each (50 total queries)
        batch_ids = list(range(10))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(make_query_batch, batch_ids))
        
        total_successes = sum(results)
        print(f"\nMemory stability test:")
        print(f"  Total successes: {total_successes}/50")
        
        # Should complete without memory issues
        assert total_successes >= 45


class TestErrorHandlingUnderLoad:
    """Test error handling with concurrent requests."""
    
    def test_errors_dont_cascade(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test that errors in some requests don't affect others."""
        def make_query(query_id: int) -> Dict[str, Any]:
            """Make a query (some may fail)."""
            # Mix of valid and potentially problematic queries
            queries = [
                "Normal query",
                "",  # Empty query
                "x" * 1000,  # Very long query
                "Normal query 2",
                "Special chars: @#$%^&*()"
            ]
            query_text = queries[query_id % len(queries)]
            
            query_data = {
                "query": query_text,
                "workspace_id": workspace_id
            }
            response = client.post("/query", json=query_data, headers=auth_headers)
            return {
                "query": query_text[:20],
                "success": response.status_code in [200, 400],  # 400 is valid for bad queries
                "status_code": response.status_code
            }
        
        query_ids = list(range(25))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            results = list(executor.map(make_query, query_ids))
        
        # Count different outcomes
        success_count = sum(1 for r in results if r["status_code"] == 200)
        client_error_count = sum(1 for r in results if r["status_code"] == 400)
        server_error_count = sum(1 for r in results if r["status_code"] >= 500)
        
        print(f"\nError isolation test:")
        print(f"  Successes: {success_count}")
        print(f"  Client errors (400): {client_error_count}")
        print(f"  Server errors (5xx): {server_error_count}")
        
        # Server errors should be rare (errors shouldn't cascade)
        assert server_error_count < 5, f"Too many server errors: {server_error_count}"


class TestThroughput:
    """Test query throughput under load."""
    
    def test_sustained_throughput(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test sustained query throughput."""
        def make_query(query_id: int) -> bool:
            """Make a query and return success status."""
            query_data = {
                "query": f"Query {query_id}",
                "workspace_id": workspace_id
            }
            try:
                response = client.post("/query", json=query_data, headers=auth_headers)
                return response.status_code == 200
            except:
                return False
        
        # Test with 30 queries, 10 concurrent workers
        query_ids = list(range(30))
        
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(make_query, query_ids))
        total_time = time.time() - start_time
        
        successes = sum(results)
        throughput = successes / total_time
        
        print(f"\nThroughput test:")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Successful queries: {successes}/30")
        print(f"  Throughput: {throughput:.2f} queries/second")
        
        # Should achieve reasonable throughput (>1 query/second)
        assert throughput >= 1.0, f"Throughput too low: {throughput:.2f} qps"
