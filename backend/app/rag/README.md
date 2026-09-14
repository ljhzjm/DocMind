# RAG

## Reranker

`PassthroughReranker` keeps retrieval order and truncates to `rag_context_top_k`.
To add bge-reranker:

1. Implement `RerankProvider.rerank()` in a new adapter.
2. Keep its model endpoint and credentials in settings/environment, never in code.
3. Extend `create_reranker()` so `RERANK_PROVIDER=bge` returns that adapter.
4. Set `RERANK_ENABLED=true` only after the adapter and health checks are ready.

## Refusal

After reranking, if the result list is empty or top1 score is lower than
`RAG_REFUSAL_THRESHOLD`, the pipeline returns `未找到相关资料` without calling
the generation model.

## Prompts

`prompts/rag_answer.j2` and `prompts/query_rewrite.j2` are versioned with code.
Do not construct these prompts inline in service methods. Prompt changes
require tests because citation parsing and JSON validation depend on them.
