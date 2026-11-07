"""Unit tests for voice splitter, sentence segmentation, and streaming adapters."""

from __future__ import annotations

import pytest

from syssathi.voice.splitter import SentenceSplitter, split_sentences_async


class TestSentenceSplitter:
    def test_basic_sentences(self):
        splitter = SentenceSplitter()
        text = "Ye pehla sentence hai. Aur ye doosra! Kya teesra bhi hai? Bilkul."
        sentences = splitter.push(text)
        assert len(sentences) == 4
        assert sentences[0] == "Ye pehla sentence hai."
        assert sentences[1] == "Aur ye doosra!"
        assert sentences[2] == "Kya teesra bhi hai?"
        assert sentences[3] == "Bilkul."

    def test_hindi_danda_delimiters(self):
        splitter = SentenceSplitter()
        text = "RAM 91% use ho rahi hai। Chrome band kar do।"
        sentences = splitter.push(text)
        assert len(sentences) == 2
        assert sentences[0] == "RAM 91% use ho rahi hai।"
        assert sentences[1] == "Chrome band kar do।"

    def test_token_streaming_chunks(self):
        splitter = SentenceSplitter()
        tokens = ["RAM ", "91% ", "use ", "ho ", "rahi ", "hai. ", "Chrome ", "band ", "karein?"]
        collected: list[str] = []
        for t in tokens:
            collected.extend(splitter.push(t))
        collected.extend(splitter.flush())

        assert len(collected) == 2
        assert collected[0] == "RAM 91% use ho rahi hai."
        assert collected[1] == "Chrome band karein?"

    @pytest.mark.asyncio
    async def test_async_generator(self):
        async def fake_token_stream():
            yield "Pehla sentence! "
            yield "Doosra "
            yield "sentence."

        sentences = [s async for s in split_sentences_async(fake_token_stream())]
        assert len(sentences) == 2
        assert sentences[0] == "Pehla sentence!"
        assert sentences[1] == "Doosra sentence."

