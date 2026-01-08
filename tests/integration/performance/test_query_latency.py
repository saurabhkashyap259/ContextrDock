"""
Performance tests for query latency (T202).

Tests query performance with p95 latency target <10s:
- Simple queries
- Complex queries
- Multi-document queries
- Large workspace queries
"""
import pytest
import time
from typing import List
from fastapi.testclient import TestClient


class TestQueryLatencyBasic:
    """Test basic query latency."""
    
    def test_simple_query_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test simple query completes within reasonable time."""
        query_data = {
            "query": "What is the project status?",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Simple queries should complete within 5 seconds
        assert latency < 5.0, f"Simple query took {latency:.2f}s, expected <5s"
    
    def test_keyword_only_query_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test keyword-only queries are fast."""
        query_data = {
            "query": "project status",
            "workspace_id": workspace_id,
            "use_vector_search": False  # Force keyword-only
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Keyword queries should be very fast (<2s)
        assert latency < 2.0, f"Keyword query took {latency:.2f}s, expected <2s"


class TestQueryLatencyComplex:
    """Test complex query latency."""
    
    def test_multi_document_query_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test queries spanning multiple documents."""
        query_data = {
            "query": "Compare the Q1 and Q2 financial results and identify trends",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Complex queries should complete within 10 seconds
        assert latency < 10.0, f"Complex query took {latency:.2f}s, expected <10s"
    
    def test_long_query_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test queries with long question text."""
        query_data = {
            "query": " ".join([
                "I need to understand the complete architecture of our system,",
                "including the database schema, API endpoints, authentication flow,",
                "deployment process, and how all the components interact with each other.",
                "Can you provide a comprehensive overview with specific details?"
            ]),
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Even long queries should complete within 10 seconds
        assert latency < 10.0, f"Long query took {latency:.2f}s, expected <10s"


class TestQueryLatencyP95:
    """Test p95 latency across multiple queries."""
    
    def test_p95_latency_target(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test that p95 latency is below 10s across varied queries."""
        queries = [
            "What is the project status?",
            "Show me recent updates",
            "Find documents about security",
            "What are the deployment steps?",
            "Compare Q1 and Q2 results",
            "List all team members",
            "Show configuration files",
            "What is the API documentation?",
            "Find bugs in issue tracker",
            "Show recent commits",
            "What are the test coverage metrics?",
            "Find design documents",
            "What is the roadmap?",
            "Show database schema",
            "Find integration guides",
            "What are the dependencies?",
            "Show environment variables",
            "Find troubleshooting guides",
            "What is the architecture?",
            "Show performance metrics"
        ]
        
        latencies: List[float] = []
        
        for query in queries:
            query_data = {
                "query": query,
                "workspace_id": workspace_id
            }
            
            start = time.time()
            response = client.post("/query", json=query_data, headers=auth_headers)
            latency = time.time() - start
            
            assert response.status_code == 200
            latencies.append(latency)
        
        # Calculate p95
        sorted_latencies = sorted(latencies)
        p95_index = int(len(sorted_latencies) * 0.95)
        p95_latency = sorted_latencies[p95_index]
        
        # Calculate other percentiles for context
        p50_latency = sorted_latencies[int(len(sorted_latencies) * 0.50)]
        p99_latency = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        
        print(f"\nLatency distribution:")
        print(f"  p50: {p50_latency:.2f}s")
        print(f"  p95: {p95_latency:.2f}s")
        print(f"  p99: {p99_latency:.2f}s")
        print(f"  max: {max(latencies):.2f}s")
        
        # p95 should be below 10 seconds
        assert p95_latency < 10.0, f"p95 latency is {p95_latency:.2f}s, expected <10s"


class TestQueryLatencyScaling:
    """Test query latency scaling with workspace size."""
    
    def test_small_workspace_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test queries in small workspace (<100 documents)."""
        query_data = {
            "query": "Find recent updates",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Small workspaces should be fast
        assert latency < 3.0, f"Small workspace query took {latency:.2f}s, expected <3s"
    
    def test_latency_consistency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test query latency consistency across multiple runs."""
        query_data = {
            "query": "What is the project status?",
            "workspace_id": workspace_id
        }
        
        latencies: List[float] = []
        
        # Run query 10 times
        for _ in range(10):
            start = time.time()
            response = client.post("/query", json=query_data, headers=auth_headers)
            latency = time.time() - start
            
            assert response.status_code == 200
            latencies.append(latency)
        
        # Calculate variance
        avg_latency = sum(latencies) / len(latencies)
        variance = sum((l - avg_latency) ** 2 for l in latencies) / len(latencies)
        std_dev = variance ** 0.5
        
        print(f"\nLatency consistency:")
        print(f"  avg: {avg_latency:.2f}s")
        print(f"  std_dev: {std_dev:.2f}s")
        print(f"  min: {min(latencies):.2f}s")
        print(f"  max: {max(latencies):.2f}s")
        
        # Latency should be consistent (std dev < 50% of average)
        assert std_dev < avg_latency * 0.5, f"High latency variance: {std_dev:.2f}s"


class TestQueryLatencyComponents:
    """Test latency of individual query components."""
    
    def test_embedding_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test embedding generation latency."""
        # This would ideally be tested via metrics or profiling
        # For now, test that queries with embedding complete reasonably
        query_data = {
            "query": "Test query for embedding latency",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Embedding + search + LLM should complete within 10s
        assert latency < 10.0
    
    def test_vector_search_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test vector search latency."""
        query_data = {
            "query": "Find documents about testing",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Vector search should be fast component (<5s total)
        assert latency < 5.0


class TestQueryLatencyEdgeCases:
    """Test query latency edge cases."""
    
    def test_empty_query_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test very short queries."""
        query_data = {
            "query": "hi",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        # Should complete quickly even if results are not great
        assert latency < 5.0
    
    def test_no_results_query_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test queries that return no relevant results."""
        query_data = {
            "query": "xyzabc123nonexistentterm456",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        # Should fail fast if no results
        assert latency < 5.0
    
    def test_special_characters_query_latency(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test queries with special characters."""
        query_data = {
            "query": "What's the @project #status? (Q1/Q2)",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        assert response.status_code == 200
        assert latency < 10.0


class TestQueryLatencyTimeout:
    """Test query timeout behavior."""
    
    def test_query_has_timeout(self, client: TestClient, workspace_id: str, auth_headers: dict):
        """Test that queries don't hang indefinitely."""
        query_data = {
            "query": "Very complex query that might take long",
            "workspace_id": workspace_id
        }
        
        start = time.time()
        response = client.post("/query", json=query_data, headers=auth_headers)
        latency = time.time() - start
        
        # Should timeout or complete within 30 seconds max
        assert latency < 30.0, f"Query took {latency:.2f}s, may need timeout"
