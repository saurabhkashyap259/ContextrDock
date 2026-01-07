"""Pagination helper for cursor-based pagination."""

import time
from dataclasses import dataclass
from typing import Iterator, List, Optional, Callable, Any, TypeVar


T = TypeVar('T')


@dataclass
class PageResult:
    """
    Result from fetching a single page of data.
    
    Attributes:
        items: List of items from this page
        next_cursor: Cursor for next page (None if last page)
        has_more: Whether more pages are available
    """
    items: List[Any]
    next_cursor: Optional[str]
    has_more: bool


class CursorPaginator:
    """
    Iterator for cursor-based pagination.
    
    Automatically fetches pages and yields individual items.
    Handles cursor management and iteration state.
    
    Example:
        def fetch_slack_messages(cursor: Optional[str]) -> PageResult:
            response = slack_client.conversations_history(
                channel="C123",
                cursor=cursor,
                limit=100
            )
            return PageResult(
                items=response["messages"],
                next_cursor=response.get("response_metadata", {}).get("next_cursor"),
                has_more=response.get("has_more", False)
            )
        
        paginator = CursorPaginator(fetch_slack_messages)
        for message in paginator:
            print(message["text"])
    """
    
    def __init__(
        self,
        fetch_func: Callable[[Optional[str]], PageResult],
        initial_cursor: Optional[str] = None
    ):
        """
        Initialize paginator.
        
        Args:
            fetch_func: Function that fetches a page given a cursor
            initial_cursor: Starting cursor (None to start from beginning)
        """
        self.fetch_func = fetch_func
        self.initial_cursor = initial_cursor
        self.current_cursor: Optional[str] = None
    
    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over all items across all pages.
        
        Yields:
            Individual items from all pages
        """
        cursor = self.initial_cursor
        
        while True:
            # Fetch page
            page = self.fetch_func(cursor)
            self.current_cursor = cursor
            
            # Yield items from this page
            for item in page.items:
                yield item
            
            # Check if more pages
            if not page.has_more or page.next_cursor is None:
                break
            
            cursor = page.next_cursor


def paginate_all(
    fetch_func: Callable[[Optional[str]], PageResult],
    initial_cursor: Optional[str] = None,
    max_pages: Optional[int] = None,
    max_items: Optional[int] = None
) -> List[Any]:
    """
    Fetch all items from all pages.
    
    Convenience function that collects all items into a list.
    Use with caution for large datasets - consider streaming with CursorPaginator instead.
    
    Args:
        fetch_func: Function that fetches a page given a cursor
        initial_cursor: Starting cursor (None to start from beginning)
        max_pages: Maximum number of pages to fetch (None for unlimited)
        max_items: Maximum number of items to collect (None for unlimited)
    
    Returns:
        List of all items from all pages
    
    Example:
        def fetch_users(cursor: Optional[str] = None) -> PageResult:
            response = api.get_users(cursor=cursor, limit=100)
            return PageResult(
                items=response["users"],
                next_cursor=response.get("next_cursor"),
                has_more=response.get("has_more", False)
            )
        
        all_users = paginate_all(fetch_users, max_items=1000)
    """
    items = []
    cursor = initial_cursor
    page_count = 0
    
    while True:
        # Check page limit
        if max_pages is not None and page_count >= max_pages:
            break
        
        # Fetch page
        page = fetch_func(cursor)
        page_count += 1
        
        # Add items (respecting max_items limit)
        for item in page.items:
            items.append(item)
            
            if max_items is not None and len(items) >= max_items:
                return items
        
        # Check if more pages
        if not page.has_more or page.next_cursor is None:
            break
        
        cursor = page.next_cursor
    
    return items


def paginate_with_retry(
    fetch_func: Callable[[Optional[str]], PageResult],
    initial_cursor: Optional[str] = None,
    max_pages: Optional[int] = None,
    max_items: Optional[int] = None,
    max_retries: int = 3,
    initial_backoff: float = 1.0
) -> List[Any]:
    """
    Fetch all items with automatic retry on failures.
    
    Implements exponential backoff for transient failures.
    Useful for unstable APIs or network conditions.
    
    Args:
        fetch_func: Function that fetches a page given a cursor
        initial_cursor: Starting cursor (None to start from beginning)
        max_pages: Maximum number of pages to fetch (None for unlimited)
        max_items: Maximum number of items to collect (None for unlimited)
        max_retries: Maximum retry attempts per page
        initial_backoff: Initial backoff delay in seconds (doubles each retry)
    
    Returns:
        List of all items from all pages
    
    Raises:
        Exception: If all retries exhausted for a page
    
    Example:
        def fetch_data(cursor: Optional[str] = None) -> PageResult:
            response = unstable_api.get_data(cursor=cursor)
            return PageResult(
                items=response["data"],
                next_cursor=response.get("cursor"),
                has_more=response.get("has_more", False)
            )
        
        # Will retry up to 3 times per page with exponential backoff
        all_data = paginate_with_retry(fetch_data, max_retries=3)
    """
    items = []
    cursor = initial_cursor
    page_count = 0
    
    while True:
        # Check page limit
        if max_pages is not None and page_count >= max_pages:
            break
        
        # Fetch page with retry logic
        page = None
        backoff = initial_backoff
        
        for attempt in range(max_retries + 1):
            try:
                page = fetch_func(cursor)
                break
            except Exception as e:
                if attempt < max_retries:
                    # Retry with exponential backoff
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    # All retries exhausted
                    raise
        
        page_count += 1
        
        # Add items (respecting max_items limit)
        for item in page.items:
            items.append(item)
            
            if max_items is not None and len(items) >= max_items:
                return items
        
        # Check if more pages
        if not page.has_more or page.next_cursor is None:
            break
        
        cursor = page.next_cursor
    
    return items
