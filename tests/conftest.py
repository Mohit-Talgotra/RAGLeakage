import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.secure_pipeline.clock import SimClock  # noqa: E402
from src.secure_pipeline.experiments import Env  # noqa: E402
from src.secure_pipeline.instrumentation import RunLogger  # noqa: E402
from src.secure_pipeline.llm_client import LLMClient  # noqa: E402
from src.secure_pipeline.mitigations import preset  # noqa: E402
from src.secure_pipeline.pipeline import Client, PipelineConfig, RAGPipeline  # noqa: E402


@pytest.fixture(scope="session")
def env():
    """Offline environment: hashed embeddings, lexical reranker. No downloads."""
    return Env.build("hash", "overlap")


@pytest.fixture
def make_pipeline(env):
    made = []

    def _make(name="full", sync="live", seed=0, **overrides):
        clock = SimClock()
        llm = LLMClient("stub", clock, random.Random(seed))
        cfg_fields = {k: overrides.pop(k) for k in list(overrides) if k in PipelineConfig.__dataclass_fields__}
        cfg = PipelineConfig(sync=sync, min_relevance=0.15, **cfg_fields)
        pipe = RAGPipeline(env.corpus, env.chunk_vecs, env.embedder, env.reranker, llm, clock,
                           preset(name, **overrides), cfg, seed=seed)
        made.append(pipe)
        return pipe, Client(pipe, "with_reranker", RunLogger())

    yield _make
    for p in made:
        p.close()
