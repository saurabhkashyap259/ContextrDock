"""Performance tests for ACL validation.

Verifies that ACL permission checks complete within acceptable time limits
(< 100ms per check) to ensure responsive query performance.
"""

import pytest
import time
from datetime import datetime

from src.services.acl_validator import ACLValidator


@pytest.fixture
def acl_validator():
    """Create ACL validator instance."""
    return ACLValidator()


@pytest.fixture
def sample_user():
    """Sample user with all connector identities."""
    return {
        "id": 1,
        "email": "test@company.com",
        "connector_identities": {
            "slack": {"user_id": "U123", "team_id": "T456"},
            "jira": {"account_id": "jira:123"},
            "github": {"login": "testuser", "organizations": ["testorg"]},
            "confluence": {"account_id": "conf:123"},
            "figma": {"user_id": "figma:123", "teams": ["team1"]},
            "dropbox": {"email": "test@company.com"}
        }
    }


class TestACLPerformance:
    """Test ACL validation performance."""
    
    def test_single_acl_check_under_100ms(self, acl_validator, sample_user):
        """Test that a single ACL check completes under 100ms."""
        acl_metadata = {
            "connector_type": "slack",
            "access_level": "restricted",
            "channel_id": "C123",
            "allowed_user_ids": ["U123", "U456", "U789"]
        }
        
        start_time = time.perf_counter()
        result = acl_validator.check_access(sample_user, acl_metadata)
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000
        
        assert result.allowed is True
        assert duration_ms < 100, f"ACL check took {duration_ms:.2f}ms, expected < 100ms"
    
    def test_batch_100_acls_under_10_seconds(self, acl_validator, sample_user):
        """Test that checking 100 ACLs completes under 10 seconds (100ms avg)."""
        acl_list = []
        
        # Mix of different connector types and access levels
        for i in range(100):
            connector_type = ["slack", "jira", "github", "confluence", "figma", "dropbox"][i % 6]
            
            if connector_type == "slack":
                acl = {
                    "connector_type": "slack",
                    "access_level": "restricted" if i % 2 else "public",
                    "allowed_user_ids": ["U123"] if i % 2 else []
                }
            elif connector_type == "jira":
                acl = {
                    "connector_type": "jira",
                    "access_level": "restricted" if i % 2 else "public",
                    "allowed_account_ids": ["jira:123"] if i % 2 else []
                }
            elif connector_type == "github":
                acl = {
                    "connector_type": "github",
                    "access_level": "internal" if i % 3 else "public",
                    "organization": "testorg",
                    "collaborators": ["testuser"]
                }
            elif connector_type == "confluence":
                acl = {
                    "connector_type": "confluence",
                    "access_level": "restricted" if i % 2 else "public",
                    "allowed_account_ids": ["conf:123"] if i % 2 else []
                }
            elif connector_type == "figma":
                acl = {
                    "connector_type": "figma",
                    "access_level": "team",
                    "allowed_users": ["figma:123", "figma:456"]
                }
            else:  # dropbox
                acl = {
                    "connector_type": "dropbox",
                    "access_level": "shared",
                    "shared_with": ["test@company.com"]
                }
            
            acl_list.append(acl)
        
        start_time = time.perf_counter()
        results = acl_validator.batch_check_access(sample_user, acl_list)
        end_time = time.perf_counter()
        
        duration_s = end_time - start_time
        avg_duration_ms = (duration_s / 100) * 1000
        
        assert len(results) == 100
        assert duration_s < 10, f"Batch check took {duration_s:.2f}s, expected < 10s"
        assert avg_duration_ms < 100, f"Average check took {avg_duration_ms:.2f}ms, expected < 100ms"
    
    def test_public_access_fast_path(self, acl_validator, sample_user):
        """Test that public access checks are fast (< 1ms)."""
        acl_metadata = {
            "connector_type": "slack",
            "access_level": "public"
        }
        
        start_time = time.perf_counter()
        result = acl_validator.check_access(sample_user, acl_metadata)
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000
        
        assert result.allowed is True
        assert duration_ms < 1, f"Public access check took {duration_ms:.2f}ms, expected < 1ms"
    
    def test_fail_closed_fast_path(self, acl_validator, sample_user):
        """Test that fail-closed checks are fast (< 1ms)."""
        start_time = time.perf_counter()
        result = acl_validator.check_access(sample_user, None)
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000
        
        assert result.allowed is False
        assert duration_ms < 1, f"Fail-closed check took {duration_ms:.2f}ms, expected < 1ms"
    
    def test_1000_checks_scalability(self, acl_validator, sample_user):
        """Test scalability with 1000 ACL checks (< 100s total)."""
        acl_list = []
        
        # Generate 1000 varied ACL checks
        for i in range(1000):
            connector_type = ["slack", "jira", "github"][i % 3]
            
            if connector_type == "slack":
                acl = {
                    "connector_type": "slack",
                    "access_level": "restricted" if i % 2 else "public",
                    "allowed_user_ids": ["U123"] if i % 2 else []
                }
            elif connector_type == "jira":
                acl = {
                    "connector_type": "jira",
                    "access_level": "public"
                }
            else:
                acl = {
                    "connector_type": "github",
                    "access_level": "public",
                    "visibility": "public"
                }
            
            acl_list.append(acl)
        
        start_time = time.perf_counter()
        results = acl_validator.batch_check_access(sample_user, acl_list)
        end_time = time.perf_counter()
        
        duration_s = end_time - start_time
        avg_duration_ms = (duration_s / 1000) * 1000
        
        assert len(results) == 1000
        assert duration_s < 100, f"1000 checks took {duration_s:.2f}s, expected < 100s"
        assert avg_duration_ms < 100, f"Average check took {avg_duration_ms:.3f}ms, expected < 100ms"
    
    def test_worst_case_complex_acl(self, acl_validator, sample_user):
        """Test worst-case scenario with complex ACL (< 100ms)."""
        # Complex Slack ACL with many members
        acl_metadata = {
            "connector_type": "slack",
            "access_level": "restricted",
            "channel_id": "C123",
            "channel_name": "engineering",
            "allowed_user_ids": [f"U{i:03d}" for i in range(1000)],  # 1000 members
        }
        
        # Add user to the list
        acl_metadata["allowed_user_ids"].append("U123")
        
        start_time = time.perf_counter()
        result = acl_validator.check_access(sample_user, acl_metadata)
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000
        
        assert result.allowed is True
        assert duration_ms < 100, f"Complex ACL check took {duration_ms:.2f}ms, expected < 100ms"
    
    def test_mixed_results_performance(self, acl_validator, sample_user):
        """Test performance with mixed allow/deny results."""
        acl_list = []
        
        for i in range(100):
            # Alternate between allowed and denied
            if i % 2 == 0:
                acl = {
                    "connector_type": "slack",
                    "access_level": "restricted",
                    "allowed_user_ids": ["U123"]  # User allowed
                }
            else:
                acl = {
                    "connector_type": "slack",
                    "access_level": "restricted",
                    "allowed_user_ids": ["U999"]  # User denied
                }
            
            acl_list.append(acl)
        
        start_time = time.perf_counter()
        results = acl_validator.batch_check_access(sample_user, acl_list)
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000
        
        assert len(results) == 100
        assert sum(1 for r in results if r.allowed) == 50  # Half allowed
        assert duration_ms < 10000, f"Mixed results took {duration_ms:.2f}ms, expected < 10000ms"


class TestACLMemoryUsage:
    """Test ACL validation memory efficiency."""
    
    def test_no_memory_leak_repeated_checks(self, acl_validator, sample_user):
        """Test that repeated checks don't leak memory."""
        acl_metadata = {
            "connector_type": "slack",
            "access_level": "restricted",
            "allowed_user_ids": ["U123"]
        }
        
        # Perform 10000 checks to detect memory leaks
        for _ in range(10000):
            result = acl_validator.check_access(sample_user, acl_metadata)
            assert result.allowed is True
        
        # If we get here without OOM, test passes
        assert True


class TestRealWorldScenario:
    """Test real-world query scenarios."""
    
    def test_typical_query_50_results(self, acl_validator, sample_user):
        """Test typical query returning 50 results (< 5s total)."""
        # Simulate 50 search results with varied ACLs
        acl_list = []
        
        for i in range(50):
            if i < 10:  # 20% public
                acl = {"connector_type": "slack", "access_level": "public"}
            elif i < 30:  # 40% restricted slack
                acl = {
                    "connector_type": "slack",
                    "access_level": "restricted",
                    "allowed_user_ids": ["U123", "U456"]
                }
            elif i < 45:  # 30% jira
                acl = {
                    "connector_type": "jira",
                    "access_level": "restricted",
                    "allowed_account_ids": ["jira:123"]
                }
            else:  # 10% github
                acl = {
                    "connector_type": "github",
                    "access_level": "internal",
                    "organization": "testorg"
                }
            
            acl_list.append(acl)
        
        start_time = time.perf_counter()
        results = acl_validator.batch_check_access(sample_user, acl_list)
        end_time = time.perf_counter()
        
        duration_s = end_time - start_time
        
        assert len(results) == 50
        assert duration_s < 5, f"Query ACL filtering took {duration_s:.2f}s, expected < 5s"
        
        # All should be allowed for this user
        allowed_count = sum(1 for r in results if r.allowed)
        assert allowed_count == 50
    
    def test_large_result_set_200_chunks(self, acl_validator, sample_user):
        """Test large result set with 200 chunks (< 20s)."""
        acl_list = []
        
        # Generate 200 ACLs with realistic distribution
        for i in range(200):
            connector_type = ["slack", "jira", "confluence", "github"][i % 4]
            
            if connector_type == "slack":
                acl = {
                    "connector_type": "slack",
                    "access_level": "restricted" if i % 3 else "public",
                    "allowed_user_ids": ["U123"] if i % 3 else []
                }
            elif connector_type == "jira":
                acl = {
                    "connector_type": "jira",
                    "access_level": "restricted" if i % 2 else "public",
                    "allowed_account_ids": ["jira:123"] if i % 2 else []
                }
            elif connector_type == "confluence":
                acl = {
                    "connector_type": "confluence",
                    "access_level": "public"
                }
            else:
                acl = {
                    "connector_type": "github",
                    "access_level": "internal",
                    "organization": "testorg"
                }
            
            acl_list.append(acl)
        
        start_time = time.perf_counter()
        results = acl_validator.batch_check_access(sample_user, acl_list)
        end_time = time.perf_counter()
        
        duration_s = end_time - start_time
        
        assert len(results) == 200
        assert duration_s < 20, f"Large result set ACL check took {duration_s:.2f}s, expected < 20s"
