"""Sentence splitter turning a token stream into finished sentences."""

from __future__ import annotations

import re
from typing import AsyncIterator, Iterator

# End-of-sentence delimiters: Latin (. ? !), Hindi danda (।), double danda (॥)
_SENTENCE_END_RE = re.compile(r"([.?!।॥]+(?:\s+|$))")


class SentenceSplitter:
    """Buffers streaming token chunks and yields complete sentences."""

    def __init__(self) -> None:
        self._buffer: str = ""

    def push(self, chunk: str) -> list[str]:
        """Push a text chunk into buffer and return any newly completed sentences."""
        self._buffer += chunk
        sentences: list[str] = []

        while True:
            match = _SENTENCE_END_RE.search(self._buffer)
            if not match:
                break
            end_pos = match.end()
            sentence = self._buffer[:end_pos].strip()
            self._buffer = self._buffer[end_pos:]
            if sentence:
                sentences.append(sentence)

        return sentences

    def flush(self) -> list[str]:
        """Flush any remaining text in the buffer as a final sentence."""
        remaining = self._buffer.strip()
        self._buffer = ""
        if remaining:
            return [remaining]
        return []


async def split_sentences_async(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Async generator consuming tokens and yielding complete sentences."""
    splitter = SentenceSplitter()
    async for token in token_stream:
        for sentence in splitter.push(token):
            yield sentence
    for sentence in splitter.flush():
        yield sentence

