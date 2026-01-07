"""Tests for pagination helper."""

import pytest
from typing import List, Dict, Any, Optional, Callable
from unittest.mock import Mock, patch

from src.connectors.sdk.pagination import (
    CursorPaginator,
    PageResult,
    paginate_all,
    paginate_with_retry
)


def test_page_result_creation():
    """Test PageResult dataclass creation."""
    items = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]
    result = PageResult(
        items=items,
        next_cursor="cursor_abc123",
        has_more=True
    )
    
    assert result.items == items
    assert result.next_cursor == "cursor_abc123"
    assert result.has_more is True


def test_page_result_last_page():
    """Test PageResult for last page with no next cursor."""
    items = [{"id": 3, "name": "Item 3"}]
    result = PageResult(
        items=items,
        next_cursor=None,
        has_more=False
    )
    
    assert result.items == items
    assert result.next_cursor is None
    assert result.has_more is False


def test_cursor_paginator_initialization():
    """Test CursorPaginator initialization."""
    def fetch_page(cursor: Optional[str]) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False)
    
    paginator = CursorPaginator(fetch_page)
    
    assert paginator.fetch_func == fetch_page
    assert paginator.initial_cursor is None


def test_cursor_paginator_with_initial_cursor():
    """Test CursorPaginator with initial cursor."""
    def fetch_page(cursor: Optional[str]) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False)
    
    paginator = CursorPaginator(fetch_page, initial_cursor="start_cursor")
    
    assert paginator.initial_cursor == "start_cursor"


def test_cursor_paginator_iterate_single_page():
    """Test iterating over single page."""
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    
    def fetch_page(cursor: Optional[str]) -> PageResult:
        return PageResult(items=items, next_cursor=None, has_more=False)
    
    paginator = CursorPaginator(fetch_page)
    all_items = list(paginator)
    
    assert len(all_items) == 3
    assert all_items == items


def test_cursor_paginator_iterate_multiple_pages():
    """Test iterating over multiple pages."""
    pages = [
        PageResult(items=[{"id": 1}, {"id": 2}], next_cursor="page2", has_more=True),
        PageResult(items=[{"id": 3}, {"id": 4}], next_cursor="page3", has_more=True),
        PageResult(items=[{"id": 5}], next_cursor=None, has_more=False)
    ]
    page_index = [0]
    
    def fetch_page(cursor: Optional[str]) -> PageResult:
        result = pages[page_index[0]]
        page_index[0] += 1
        return result
    
    paginator = CursorPaginator(fetch_page)
    all_items = list(paginator)
    
    assert len(all_items) == 5
    assert all_items == [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}]


def test_cursor_paginator_with_initial_cursor_start():
    """Test paginator starting from specific cursor."""
    def fetch_page(cursor: Optional[str]) -> PageResult:
        if cursor == "page2":
            return PageResult(items=[{"id": 3}, {"id": 4}], next_cursor=None, has_more=False)
        return PageResult(items=[{"id": 1}, {"id": 2}], next_cursor="page2", has_more=True)
    
    # Start from page2
    paginator = CursorPaginator(fetch_page, initial_cursor="page2")
    all_items = list(paginator)
    
    assert len(all_items) == 2
    assert all_items == [{"id": 3}, {"id": 4}]


def test_cursor_paginator_empty_pages():
    """Test handling empty pages."""
    def fetch_page(cursor: Optional[str]) -> PageResult:
        if cursor is None:
            return PageResult(items=[], next_cursor="page2", has_more=True)
        return PageResult(items=[{"id": 1}], next_cursor=None, has_more=False)
    
    paginator = CursorPaginator(fetch_page)
    all_items = list(paginator)
    
    # Should skip empty page and continue
    assert len(all_items) == 1
    assert all_items == [{"id": 1}]


def test_paginate_all_function():
    """Test paginate_all helper function."""
    pages = [
        PageResult(items=[1, 2], next_cursor="page2", has_more=True),
        PageResult(items=[3, 4], next_cursor="page3", has_more=True),
        PageResult(items=[5], next_cursor=None, has_more=False)
    ]
    page_index = [0]
    
    def fetch_page(cursor: Optional[str] = None) -> PageResult:
        result = pages[page_index[0]]
        page_index[0] += 1
        return result
    
    all_items = paginate_all(fetch_page)
    
    assert all_items == [1, 2, 3, 4, 5]


def test_paginate_all_with_max_pages():
    """Test paginate_all with max_pages limit."""
    def fetch_page(cursor: Optional[str] = None) -> PageResult:
        return PageResult(items=[1, 2], next_cursor="next", has_more=True)
    
    all_items = paginate_all(fetch_page, max_pages=2)
    
    # Should stop after 2 pages
    assert len(all_items) == 4  # 2 items per page * 2 pages


def test_paginate_all_with_max_items():
    """Test paginate_all with max_items limit."""
    pages = [
        PageResult(items=[1, 2, 3], next_cursor="page2", has_more=True),
        PageResult(items=[4, 5, 6], next_cursor="page3", has_more=True),
        PageResult(items=[7, 8, 9], next_cursor=None, has_more=False)
    ]
    page_index = [0]
    
    def fetch_page(cursor: Optional[str] = None) -> PageResult:
        result = pages[page_index[0]]
        page_index[0] += 1
        return result
    
    all_items = paginate_all(fetch_page, max_items=5)
    
    # Should stop at 5 items (not 6)
    assert len(all_items) == 5
    assert all_items == [1, 2, 3, 4, 5]


def test_paginate_with_retry_success():
    """Test paginate_with_retry on successful pagination."""
    pages = [
        PageResult(items=[1, 2], next_cursor="page2", has_more=True),
        PageResult(items=[3], next_cursor=None, has_more=False)
    ]
    page_index = [0]
    
    def fetch_page(cursor: Optional[str] = None) -> PageResult:
        result = pages[page_index[0]]
        page_index[0] += 1
        return result
    
    all_items = paginate_with_retry(fetch_page)
    
    assert all_items == [1, 2, 3]


def test_paginate_with_retry_handles_temporary_failure():
    """Test paginate_with_retry retries on temporary failure."""
    call_count = [0]
    
    def fetch_page(cursor: Optional[str] = None) -> PageResult:
        call_count[0] += 1
        
        # Fail first 2 calls, succeed on 3rd
        if call_count[0] < 3:
            raise Exception("Temporary API error")
        
        return PageResult(items=[1, 2], next_cursor=None, has_more=False)
    
    all_items = paginate_with_retry(fetch_page, max_retries=3)
    
    assert all_items == [1, 2]
    assert call_count[0] == 3  # Should have retried


def test_paginate_with_retry_fails_after_max_retries():
    """Test paginate_with_retry gives up after max retries."""
    def fetch_page(cursor: Optional[str] = None) -> PageResult:
        raise Exception("Persistent API error")
    
    with pytest.raises(Exception, match="Persistent API error"):
        paginate_with_retry(fetch_page, max_retries=2)


@patch('time.sleep')
def test_paginate_with_retry_uses_backoff(mock_sleep):
    """Test paginate_with_retry uses exponential backoff."""
    call_count = [0]
    
    def fetch_page(cursor: Optional[str] = None) -> PageResult:
        call_count[0] += 1
        
        if call_count[0] < 3:
            raise Exception("API error")
        
        return PageResult(items=[1], next_cursor=None, has_more=False)
    
    paginate_with_retry(fetch_page, max_retries=3, initial_backoff=1)
    
    # Should have slept with exponential backoff
    assert mock_sleep.call_count >= 2
    # First retry: 1s, second retry: 2s
    sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
    assert sleep_calls[0] == 1
    assert sleep_calls[1] == 2


def test_cursor_paginator_get_current_cursor():
    """Test getting current cursor during iteration."""
    pages = [
        PageResult(items=[1, 2], next_cursor="cursor_2", has_more=True),
        PageResult(items=[3, 4], next_cursor="cursor_3", has_more=True),
        PageResult(items=[5], next_cursor=None, has_more=False)
    ]
    page_index = [0]
    
    def fetch_page(cursor: Optional[str]) -> PageResult:
        result = pages[page_index[0]]
        page_index[0] += 1
        return result
    
    paginator = CursorPaginator(fetch_page)
    
    # Get iterator
    iterator = iter(paginator)
    
    # Get first item
    next(iterator)
    assert paginator.current_cursor is None  # First page
    
    # Get third item (which triggers second page fetch)
    next(iterator)
    next(iterator)
    assert paginator.current_cursor == "cursor_2"


def test_page_result_from_api_response():
    """Test creating PageResult from typical API response."""
    # Simulate Slack-style API response
    api_response = {
        "ok": True,
        "messages": [
            {"ts": "1", "text": "Message 1"},
            {"ts": "2", "text": "Message 2"}
        ],
        "response_metadata": {
            "next_cursor": "dXNlcjpV"
        }
    }
    
    result = PageResult(
        items=api_response["messages"],
        next_cursor=api_response["response_metadata"]["next_cursor"],
        has_more=bool(api_response["response_metadata"]["next_cursor"])
    )
    
    assert len(result.items) == 2
    assert result.next_cursor == "dXNlcjpV"
    assert result.has_more is True


def test_page_result_from_github_style_response():
    """Test creating PageResult from GitHub-style Link header pagination."""
    # GitHub uses Link headers for pagination
    items = [{"id": 1}, {"id": 2}]
    
    # Simulate having parsed Link header
    next_url = "https://api.github.com/repos/owner/repo/issues?page=2"
    
    result = PageResult(
        items=items,
        next_cursor=next_url,  # GitHub uses full URLs
        has_more=True
    )
    
    assert len(result.items) == 2
    assert "page=2" in result.next_cursor


def test_cursor_paginator_stop_iteration():
    """Test that paginator properly stops when no more pages."""
    def fetch_page(cursor: Optional[str]) -> PageResult:
        return PageResult(items=[1, 2, 3], next_cursor=None, has_more=False)
    
    paginator = CursorPaginator(fetch_page)
    iterator = iter(paginator)
    
    # Consume all items
    items = []
    for item in iterator:
        items.append(item)
    
    # Should have stopped after 3 items
    assert len(items) == 3
    
    # Next iteration should raise StopIteration
    with pytest.raises(StopIteration):
        next(iterator)
