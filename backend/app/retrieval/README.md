# Retrieval

## Embedding abstraction

`EmbeddingProvider` isolates retrieval from model providers. The default
`LLMGatewayEmbeddingProvider` calls `LLMRouter` with `LLMTask.EMBEDDING`,
so it still follows the project rule that all model calls go through
`app/llm/`.

## Switch to local bge-m3

Run bge-m3 behind any OpenAI-compatible local server, for example Ollama,
vLLM, or Xinference. Then add a provider/model entry to
`app/llm/models.toml` and point the `embedding` route to it. A local
Ollama-style configuration is:

```toml
[providers.local]
base_url = "http://127.0.0.1:11434/v1"
api_key_env = "LOCAL_LLM_API_KEY"
timeout_seconds = 60
max_retries = 2
retry_backoff_seconds = 0.5

[models.bge_m3]
provider = "local"
model = "bge-m3"

[routes]
embedding = "bge_m3"
```

Some local servers require a non-empty placeholder API key. Put it in the
local `.env` under `LOCAL_LLM_API_KEY`; never commit a real key.

The database vector column is fixed at 1024 dimensions, so the selected
bge-m3 endpoint must expose 1024-dimensional embeddings. If a deployment
uses another dimension, add an explicit migration before switching models.

## BM25 formula

The BM25 implementation follows Robertson and Zaragoza,
"The Probabilistic Relevance Framework: BM25 and Beyond" (2009), section 4.1.
The IDF uses the Lucene-style smoothing:

```text
idf(t) = log(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
score(d, q) = sum(idf(t) * tf(t,d) * (k1 + 1) /
                  (tf(t,d) + k1 * (1 - b + b * |d| / avgdl)))
```

Defaults are `k1=1.5` and `b=0.75`. `chunk_terms` stores the inverted
postings as `(term, chunk_id, term_frequency)`.
