self.chunker = SemanticChunker(
    embedding_function=self.embedding_service.embed_text,
    chunk_size=512, threshold=0.5, min_sentences_per_chunk=3,
)

def chunk_text_with_pages(self, text, metadata):
    protected_text, table_markers = self._protect_tables(text)
    chunks_result = self.chunker.chunk(protected_text)
    page_boundaries = self._extract_page_boundaries(protected_text, metadata)
    for idx, chunk in enumerate(chunks_result):
        chunk_text = self._restore_tables(chunk.text, table_markers)
        chunk_pages = self._get_chunk_pages(chunk.start_index, chunk.end_index, page_boundaries)
        # ... lưu chunk kèm metadata: pages, content_type, has_table

-----------

def _describe_rendered_image(self, image_path, image, page_number):
    response = self.caption_client.models.generate_content(
        model=self.image_caption_model,
        contents=[image_part, prompt],
        config=types.GenerateContentConfig(temperature=0, max_output_tokens=4096),
    )
    return self._validated_visual_caption_text(response.text, image_path)


-----------


class EmbeddingService:
    def embed_text(self, text):
        result = self.client.models.embed_content(model="gemini-embedding-001", contents=text)
        return result.embeddings[0].values

def search_similar(self, query_embedding, notebook_id, limit=5, document_name=None):
    rpc_params = {"query_embedding": query_embedding,
                  "target_notebook_id": notebook_id, "match_count": limit}
    return self.client.rpc("match_documents", rpc_params).execute().data


-----------

def _retrieve_multi_document(self, query, query_embedding):
    # Stage 1: Quét nhanh 2 chunks/tài liệu -> chọn Top 5 tài liệu
    for doc_name in all_documents:
        best_similarity = max(c["similarity"] for c in 
            self.doc_repo.search_similar(query_embedding, notebook_id, limit=2, document_name=doc_name))
        document_scores[doc_name] = best_similarity
    top_docs = sorted(document_scores.items(), key=lambda x: x[1], reverse=True)[:5]

    # Stage 2: Đào sâu 8 chunks/tài liệu trong Top 5 -> ~40 chunks
    deep_results = []
    for doc_name, _ in top_docs:
        deep_results.extend(self.doc_repo.search_similar(..., limit=8, document_name=doc_name))

    # Tái xếp hạng bằng Cross-Encoder
    return self._get_reranker().rerank(query, deep_results, top_k=self.top_k)


-------------

class RerankerService:
    def __init__(self, model_name="BAAI/bge-reranker-v2-m3", force_cpu=False):
        self.model = CrossEncoder(model_name, device="cpu" if force_cpu else ...)

    def rerank(self, query, chunks, top_k=10):
        pairs = [(query, c["content"][:1000]) for c in chunks]
        scores = self.model.predict(pairs)
        return sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[:top_k]


---------------

class AssessQueryComplexity(dspy.Signature):
    question: str = dspy.InputField()
    complexity: Literal["simple", "complex"] = dspy.OutputField()

class AdaptiveRAG(dspy.Module):
    def forward(self, question, doc_names=None):
        if doc_names and len(doc_names) <= 2:  # Phạm vi nhỏ -> bỏ qua đánh giá
            return self.single_hop(question=question, doc_names=doc_names)
        assessment = self.assess_complexity(question=question)
        if assessment.complexity == "complex":
            return self.multi_hop(question=question, doc_names=doc_names)
        return self.single_hop(question=question, doc_names=doc_names)


---------------


class MultiHopRAG(dspy.Module):
    def forward(self, question, doc_names=None):
        for hop in range(max_hops):
            search_query = question if hop == 0 else self.generate_query(context, question).query
            chunks = self.retreival_service.retrieve(query=search_query)
            all_chunks.extend(chunks)
        return self.generate_answer(context=format_context(all_chunks), question=question)


-----------------------

# Bước 1: Sinh kịch bản dạng JSON
response = genai_client.models.generate_content(
    model=model, contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=7000,
    ),
)

# Bước 2: Render TTS với Gemini multi-speaker (ví dụ 2 người dẫn)
speech_config = types.SpeechConfig(
    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
        speaker_voice_configs=[
            types.SpeakerVoiceConfig(speaker="Speaker A", voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore"))),
            types.SpeakerVoiceConfig(speaker="Speaker B", voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck"))),
        ]
    )
)

response = genai_client.models.generate_content(
    model=tts_model, contents=tts_prompt,
    config=types.GenerateContentConfig(response_modality=["AUDIO"], speech_config=speech_config),
)

# Bước 3: Nén WAV thành M4A bằng FFmpeg
subprocess.run(
    ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "aac", "-b:a", "96k", str(m4a_path)],
    capture_output=True, timeout=300, check=False,
)


-----------------

def _generate_deck(*, genai_client, model, context, document_names, coverage_topics):
    outline = _generate_story_outline(genai_client, model, context, ...)
    deck = _compose_deck(genai_client, model, context, outline=outline, ...)
    return deck, outline

def render_deck_pdf_with_browser(deck, pdf_path):
    with sync_playwright() as playwright:
        # Mở trình duyệt ẩn và tải giao diện React
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(html_path.as_uri(), wait_until="domcontentloaded")

        # Tiêm dữ liệu JSON vào React để render
        page.evaluate("deck => window.renderSlideDeck(deck)", deck)
        page.wait_for_function("window.__SLIDE_RENDER_READY__ === true")

        # Chụp ảnh từng slide và lưu thành PDF
        images = []
        for index in range(page_count):
            screenshot = page.locator(".slide-render-page").nth(index).screenshot(type="png")
            images.append(Image.open(io.BytesIO(screenshot)).convert("RGB"))
        images[0].save(pdf_path, "PDF", resolution=288, save_all=True, append_images=images[1:])