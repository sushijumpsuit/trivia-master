"""A tiny deterministic embedding model for tests: word counts hashed into 64 slots.

Texts that share words get similar vectors. Lets the ChromaDB tests run without downloading
the real model (all-MiniLM-L6-v2).
"""
import hashlib, math, re
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
class HashEF(EmbeddingFunction):
    """Bag-of-words hashing embedding (not meaningful, just deterministic)."""
    def __init__(self): pass
    def __call__(self, input: Documents) -> Embeddings:
        out=[]
        for text in input:
            v=[0.0]*64
            for w in re.findall(r"[a-z0-9']+", text.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(),16)%64]+=1
            n=math.sqrt(sum(x*x for x in v)) or 1.0
            out.append([x/n for x in v])
        return out
    @staticmethod
    def name(): return "hash-test"
    def get_config(self): return {}
    @staticmethod
    def build_from_config(config): return HashEF()
