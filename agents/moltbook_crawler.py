import asyncio
import os
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

import httpx
from reader_worker import QuarantineReaderWorker
from security_filters import SimHashEngine

PROXY_URL = os.getenv("HTTP_PROXY", "http://egress-filter-proxy:3128")
ALLOWED_HOST = "www.moltbook.com"


class MoltbookPaginatedCrawler:
    """
    Cliente asíncrono endurecido para recorrer hilos de Moltbook a través del Proxy Squid.
    Incorpora presupuestos de ingesta (anti-flooding) y deduplicación temprana por SimHash.
    """

    def __init__(
        self,
        session_nonce: str,
        max_pages: int = 10,
        max_total_posts: int = 200,
        max_concurrency: int = 3,
        request_delay_sec: float = 0.75,
    ):
        self.worker = QuarantineReaderWorker(session_nonce=session_nonce)
        self.simhash = SimHashEngine()
        self.max_pages = max_pages
        self.max_total_posts = max_total_posts
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.request_delay_sec = request_delay_sec
        self.seen_simhashes: list[str] = []
        self.seen_post_ids: set[str] = set()

        # Métricas de telemetría de la misión
        self.stats = {
            "pages_fetched": 0,
            "posts_scanned": 0,
            "posts_deduplicated_sybil_early": 0,
            "posts_forwarded_to_control": 0,
        }

    def _verify_target_domain(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise ValueError(f"Violación de perímetro: intento de conexión a host no permitido ({url})")

    def _is_near_duplicate(self, text: str, max_hamming: int = 5) -> bool:
        """Filtra clones exactos o paráfrasis Sybil antes de invocar al LLM Lector."""
        fp = self.simhash.compute_hex(text)
        for existing_fp in self.seen_simhashes:
            if self.simhash.hamming_distance(fp, existing_fp) <= max_hamming:
                return True
        self.seen_simhashes.append(fp)
        return False

    async def _fetch_page_with_backoff(self, client: httpx.AsyncClient, url: str, params: dict) -> dict:
        self._verify_target_domain(url)
        async with self.semaphore:
            await asyncio.sleep(self.request_delay_sec)
            for attempt in range(3):
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    backoff = (2 ** attempt) * 1.5
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            raise RuntimeError(f"Rate limit persistente al consultar {url}")

    async def stream_thread_posts(self, topic_query: str) -> AsyncGenerator[dict, None]:
        """Pagina los resultados de búsqueda/hilos de Moltbook respetando el presupuesto máximo."""
        base_api_url = f"https://{ALLOWED_HOST}/api/v1/threads/search"
        cursor: str | None = None

        async with httpx.AsyncClient(
            proxy=PROXY_URL,
            timeout=15.0,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "ResearchAgent-ReadOnly/1.0"},
        ) as client:
            for page_idx in range(self.max_pages):
                if self.stats["posts_scanned"] >= self.max_total_posts:
                    break

                params = {"q": topic_query, "limit": 25}
                if cursor:
                    params["cursor"] = cursor

                data = await self._fetch_page_with_backoff(client, base_api_url, params)
                self.stats["pages_fetched"] += 1

                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    if self.stats["posts_scanned"] >= self.max_total_posts:
                        break
                    post_id = str(item.get("id", ""))
                    if not post_id or post_id in self.seen_post_ids:
                        continue

                    self.seen_post_ids.add(post_id)
                    self.stats["posts_scanned"] += 1
                    yield item

                cursor = data.get("next_cursor")
                if not cursor:
                    break

    async def execute_mission(self, topic_query: str) -> dict:
        """Ejecuta el ciclo completo de lectura, filtrado temprano, extracción GBNF y envío al Plano Privilegiado."""
        async for raw_post in self.stream_thread_posts(topic_query):
            content = str(raw_post.get("content", ""))[:4000]  # Truncado duro anti-flooding

            # Poda temprana de clones Sybil antes de gastar inferencia LLM
            if self._is_near_duplicate(content):
                self.stats["posts_deduplicated_sybil_early"] += 1
                continue

            post_meta = {
                "post_id": raw_post["id"],
                "agent_id": raw_post["author_id"],
                "account_age_days": int(raw_post.get("author_age_days", 0)),
                "timestamp": raw_post["created_at"],
                "content": content,
            }

            # Ejecutar extracción en hilo separado para no bloquear el event loop durante inferencia GBNF
            extracted_json = await asyncio.to_thread(self.worker.process_post, post_meta)
            await asyncio.to_thread(self.worker.forward_to_control_plane, extracted_json)
            self.stats["posts_forwarded_to_control"] += 1

        return self.stats
