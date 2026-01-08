"""Text chunking utility for document processing."""


from langchain.text_splitter import RecursiveCharacterTextSplitter


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """
    Split text into overlapping chunks for embedding.

    Uses LangChain's RecursiveCharacterTextSplitter which attempts to:
    1. Split on paragraphs first
    2. Then sentences
    3. Then words
    4. Finally characters

    This preserves semantic boundaries better than naive character splitting.

    Args:
        text: Input text to chunk
        chunk_size: Target size in characters (roughly 250 tokens for 1000 chars)
        chunk_overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks

    Example:
        >>> text = "This is a long document..." * 100
        >>> chunks = chunk_text(text, chunk_size=500, chunk_overlap=100)
        >>> len(chunks)
        15
    """
    if not text or not text.strip():
        return [] if not text else [text]

    # Configure splitter with semantic separators
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=[
            "\n\n",  # Paragraphs
            "\n",    # Lines
            ". ",    # Sentences
            "! ",
            "? ",
            "; ",
            ", ",    # Clauses
            " ",     # Words
            "",      # Characters (fallback)
        ],
    )

    chunks = splitter.split_text(text)
    return chunks
