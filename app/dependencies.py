from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings
from app.core.planning.recommendation_planner import RecommendationPlanner
from app.core.query_understanding.service import QueryUnderstandingService
from app.core.response_generation.service import ResponseGenerator
from app.core.reranking.reranker import SemanticReranker
from app.core.retrieval.bm25_retriever import BM25Retriever
from app.core.retrieval.dense_retriever import DenseRetriever
from app.core.retrieval.rrf_fusion import HybridRetriever
from app.core.verification.live_product_verifier import LiveProductVerifier
from app.indexing.bm25_indexer import BM25Indexer
from app.indexing.embedding_builder import OpenAIEmbeddingClient, UnavailableEmbeddingClient
from app.indexing.index_builder import IndexBuilder
from app.indexing.qdrant_indexer import QdrantIndexer
from app.ingestion.product_ingestion import ProductIngestion
from app.ingestion.visual_interpretation_import import VisualInterpretationImporter
from app.integrations.kapruka.client import McpKaprukaClient
from app.integrations.llm.client import OpenAIStructuredLLMClient, UnavailableLLMClient
from app.integrations.llm.reliable_executor import ReliableLLMExecutor
from app.integrations.qdrant.client import QdrantVectorStore
from app.integrations.supabase.product_cache import SupabaseProductCache
from app.optimizers.gift_box_optimizer import GiftBoxOptimizer
from app.orchestration.recommendation_orchestrator import RecommendationOrchestrator
from app.repositories.catalogue_repository import JsonCatalogueRepository
from app.sessions.store import InMemorySessionStore
from app.workflows.gift_box.context_resolver import GiftBoxContextResolver
from app.workflows.gift_box.workflow import GiftBoxWorkflow
from app.workflows.smart_shopping.workflow import SmartShoppingWorkflow


@dataclass
class Container:
    settings: Settings
    sessions: InMemorySessionStore
    repository: JsonCatalogueRepository
    kapruka: McpKaprukaClient
    product_cache: SupabaseProductCache
    qdrant_store: QdrantVectorStore
    product_ingestion: ProductIngestion
    visual_importer: VisualInterpretationImporter
    index_builder: IndexBuilder
    orchestrator: RecommendationOrchestrator

    async def close(self) -> None:
        await self.kapruka.close()
        await self.product_cache.close()
        await self.qdrant_store.close()


def build_container(settings: Settings) -> Container:
    repository = JsonCatalogueRepository(settings.catalogue_dir)
    sessions = InMemorySessionStore()
    kapruka = McpKaprukaClient(
        url=settings.kapruka_mcp_url,
        command=settings.kapruka_mcp_command,
        args=settings.kapruka_mcp_args,
        delivery_tool=settings.kapruka_delivery_tool,
        timeout_seconds=settings.kapruka_timeout_seconds,
        max_attempts=settings.kapruka_max_attempts,
        rate_limit_per_minute=settings.kapruka_rate_limit_per_minute,
    )
    qdrant_store = QdrantVectorStore(
        settings.qdrant_url,
        settings.qdrant_api_key,
        settings.qdrant_collection_prefix,
        settings.embedding_dimension,
        timeout_seconds=settings.qdrant_timeout_seconds,
    )
    product_cache = SupabaseProductCache(
        settings.supabase_url,
        settings.supabase_secret_key,
        settings.supabase_product_table,
        timeout_seconds=settings.qdrant_timeout_seconds,
    )
    if settings.openai_api_key:
        embeddings = OpenAIEmbeddingClient(
            settings.openai_api_key,
            settings.embedding_model,
            settings.embedding_dimension,
            settings.openai_timeout_seconds,
        )
        llm_client = OpenAIStructuredLLMClient(
            settings.openai_api_key, settings.openai_timeout_seconds
        )
    else:
        embeddings = UnavailableEmbeddingClient()
        llm_client = UnavailableLLMClient()
    executor = ReliableLLMExecutor(
        llm_client,
        settings.llm_primary_model,
        settings.llm_fallback_models,
        settings.llm_max_attempts_per_model,
    )
    bm25_indexer = BM25Indexer(settings.bm25_dir)
    qdrant_indexer = QdrantIndexer(qdrant_store, embeddings)
    index_builder = IndexBuilder(repository, qdrant_indexer, bm25_indexer)
    hybrid = HybridRetriever(
        DenseRetriever(qdrant_store, embeddings, settings.dense_top_k),
        BM25Retriever(bm25_indexer, repository, settings.bm25_top_k),
        settings.rrf_k,
    )
    response_generator = ResponseGenerator()
    orchestrator = RecommendationOrchestrator(
        sessions=sessions,
        repository=repository,
        query_understanding=QueryUnderstandingService(executor),
        gift_box_context=GiftBoxContextResolver(),
        planner=RecommendationPlanner(executor, settings.fused_top_k),
        retriever=hybrid,
        verifier=LiveProductVerifier(
            product_cache,
            repository,
            settings.mcp_verification_concurrency,
            settings.mcp_broad_failure_ratio,
        ),
        reranker=SemanticReranker(executor),
        kapruka=kapruka,
        smart_shopping=SmartShoppingWorkflow(
            settings.max_smart_shopping_products, response_generator
        ),
        gift_box=GiftBoxWorkflow(GiftBoxOptimizer(), response_generator),
        fused_top_k=settings.fused_top_k,
        smart_target=settings.max_smart_shopping_products,
    )
    return Container(
        settings=settings,
        sessions=sessions,
        repository=repository,
        kapruka=kapruka,
        product_cache=product_cache,
        qdrant_store=qdrant_store,
        product_ingestion=ProductIngestion(repository, kapruka, settings.mcp_verification_concurrency),
        visual_importer=VisualInterpretationImporter(repository),
        index_builder=index_builder,
        orchestrator=orchestrator,
    )
