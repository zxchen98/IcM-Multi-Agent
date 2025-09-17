import os
import json
import hashlib
from typing import List, Tuple, Dict

import hnswlib
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment from repository root .env explicitly
load_dotenv()

# Simple sqlite-backed metadata store for persistence of ids and file mapping
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "tsg_vector_store.db"
INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "tsg_index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

EMBEDDING_DIM = 3072
INDEX_PATH = INDEX_DIR / "tsg_hnsw_index.bin"


def _hash_content(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class TSGVectorStore:
    def __init__(self, tsg_root: str = "data/tsgs"):
        self.tsg_root = Path(tsg_root)
        self.db_path = DB_PATH
        self.index_path = INDEX_PATH
        self.dim = EMBEDDING_DIM
        self._ensure_db()

        # hnsw index and id mapping cache
        self.index = None
        self.id_to_meta = {}

        # load existing index if present
        if self.index_path.exists():
            self._load_index()
        else:
            self._init_index()

        self._openai_client = None  # will be lazy-initialized

    def _ensure_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tsg_meta (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                title TEXT,
                hash TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def _init_index(self):
        p = hnswlib.Index(space='cosine', dim=self.dim)
        # initial max elements - we'll allow growth using resize_index
        p.init_index(max_elements=10000, ef_construction=200, M=16)
        p.set_ef(50)
        self.index = p

    def _load_index(self):
        p = hnswlib.Index(space='cosine', dim=self.dim)
        p.load_index(str(self.index_path))
        p.set_ef(50)
        self.index = p

        # load metadata from sqlite
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, path, title FROM tsg_meta")
        rows = cur.fetchall()
        for r in rows:
            self.id_to_meta[r[0]] = {"path": r[1], "title": r[2]}
        conn.close()

    def _save_index(self):
        if self.index is not None:
            self.index.save_index(str(self.index_path))

    def _get_embedding(self, text: str) -> List[float]:
        # Ensure OpenAI client initialized and configured for Azure OpenAI
        self._ensure_openai_client()

        deployment = os.getenv("AOAI_EMBEDDING_DEPLOYMENT_NAME")
        if not deployment:
            raise RuntimeError("AOAI_EMBEDDING_DEPLOYMENT_NAME not set in environment")

        resp = self._openai_client.embeddings.create(model=deployment, input=text)
        vec = resp.data[0].embedding

        # Normalize to Python list of floats
        try:
            vec_list = [float(x) for x in vec]
        except Exception:
            raise RuntimeError("Embedding returned in unexpected format; expected iterable of numbers.")

        if len(vec_list) != self.dim:
            raise RuntimeError(f"Wrong dimensionality of embedding: got {len(vec_list)}, expected {self.dim}. "
                               "Check that AOAI_EMBEDDING_DEPLOYMENT_NAME points to an embeddings deployment.")

        return vec_list

    def _ensure_openai_client(self):
        if self._openai_client is not None:
            return

        
        api_key = os.getenv("AOAI_EMBEDDING_API_KEY")
        endpoint = os.getenv("AOAI_EMBEDDING_ENDPOINT")
        api_version = os.getenv("AOAI_EMBEDDING_API_VERSION", "2023-06-01-preview")

        if not api_key or not endpoint or not os.getenv("AOAI_EMBEDDING_DEPLOYMENT_NAME"):
            raise RuntimeError(
                "Missing Azure OpenAI configuration. Ensure AOAI_EMBEDDING_API_KEY, AOAI_EMBEDDING_ENDPOINT and AOAI_EMBEDDING_DEPLOYMENT_NAME are set."
            )

        # instantiate client
        self._openai_client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version
        )

    def _scan_tsg_files(self) -> List[Tuple[str, str, str]]:
        # returns list of tuples (id, title, content)
        items = []
        for root, dirs, files in os.walk(self.tsg_root):
            for f in files:
                if f.lower().endswith('.md') or f.lower().endswith('.txt'):
                    p = Path(root) / f
                    content = p.read_text(encoding='utf-8')
                    title = f
                    id_ = str(p.relative_to(self.tsg_root)).replace('\\', '/')
                    items.append((id_, title, content))
        return items

    def _get_db_hash(self, id_: str) -> str:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT hash FROM tsg_meta WHERE id = ?", (id_,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def _upsert_meta(self, id_: str, path: str, title: str, hash_: str):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO tsg_meta (id, path, title, hash) VALUES (?, ?, ?, ?)",
            (id_, path, title, hash_),
        )
        conn.commit()
        conn.close()

    def incremental_import(self) -> int:
        """Scan folder, compute embeddings for new/changed files, and add to index incrementally."""
        items = self._scan_tsg_files()
        to_add = []  # tuples of (id, title, content, embedding)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        for id_, title, content in items:
            h = _hash_content(content)
            cur.execute("SELECT hash FROM tsg_meta WHERE id = ?", (id_,))
            row = cur.fetchone()
            if row and row[0] == h:
                # unchanged
                continue
            # compute embedding
            vec = self._get_embedding(content)
            to_add.append((id_, title, content, vec, h))

        # ensure index has capacity
        existing_count = len(self.id_to_meta)
        needed = existing_count + len(to_add)
        if self.index is None:
            self._init_index()
        # resize if needed
        if needed > self.index.get_max_elements():
            self.index.resize_index(needed * 2)

        # add items to index
        for (id_, title, content, vec, h) in to_add:
            idx = self._id_to_int(id_)
            self.index.add_items([vec], [idx])
            self._id_to_meta_store(id_, {"path": str(self.tsg_root / id_), "title": title})
            cur.execute(
                "INSERT OR REPLACE INTO tsg_meta (id, path, title, hash) VALUES (?, ?, ?, ?)",
                (id_, str(self.tsg_root / id_), title, h),
            )

        conn.commit()
        conn.close()

        # persist index to disk
        self._save_index()
        return len(to_add)

    def _id_to_int(self, id_: str) -> int:
        # Convert id hash to deterministic integer within range
        # hnswlib expects int labels; keep mapping in sqlite via rowid if needed
        # We'll use first 8 bytes of sha256 as int
        hv = hashlib.sha256(id_.encode('utf-8')).hexdigest()[:16]
        return int(hv, 16)

    def _id_to_meta_store(self, id_: str, meta: Dict):
        self.id_to_meta[id_] = meta

    def query(self, text: str, k: int = 2) -> List[Dict]:
        vec = self._get_embedding(text)
        labels, distances = self.index.knn_query([vec], k=k)
        results = []
        for label, dist in zip(labels[0], distances[0]):
            # reverse label to id (we stored id_to_meta by id)
            # here we need to map int label back to id — we stored id as string keys; so find matching key
            id_match = None
            for idk in self.id_to_meta.keys():
                if self._id_to_int(idk) == label:
                    id_match = idk
                    break
            if id_match:
                meta = self.id_to_meta[id_match]
                results.append({"id": id_match, "title": meta.get("title"), "path": meta.get("path"), "score": float(dist)})
        return results


# Global TSG store instance (lazy-loaded)
_tsg_store = None

def get_tsg_store():
    """Lazy initialization of TSG Vector Store"""
    global _tsg_store
    if _tsg_store is None:
        tsg_root = os.path.join(os.path.dirname(__file__), '..', 'data', 'tsgs')
        _tsg_store = TSGVectorStore(tsg_root=tsg_root)
    return _tsg_store

def extract_solution_from_tsg(file_path: str) -> str:
    """
    Extract the Solution section from a TSG markdown file
    
    Args:
        file_path: Path to the TSG markdown file
        
    Returns:
        str: Content of the Solution section, or empty string if not found
    """
    try:
        if not os.path.exists(file_path):
            return ""
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split content into lines
        lines = content.split('\n')
        
        # Find the Solution section
        solution_start = -1
        solution_end = len(lines)
        
        for i, line in enumerate(lines):
            # Look for "## Solution" header
            if line.strip().lower().startswith('## solution'):
                solution_start = i + 1
            # Look for next ## header after Solution
            elif solution_start != -1 and line.strip().startswith('## ') and not line.strip().lower().startswith('## solution'):
                solution_end = i
                break
        
        if solution_start == -1:
            return ""
        
        # Extract solution content
        solution_lines = lines[solution_start:solution_end]
        
        # Remove empty lines from the beginning and end
        while solution_lines and not solution_lines[0].strip():
            solution_lines.pop(0)
        while solution_lines and not solution_lines[-1].strip():
            solution_lines.pop()
        
        return '\n'.join(solution_lines)
        
    except Exception as e:
        print(f"❌ Error extracting solution from {file_path}: {e}")
        return ""

def search_tsg_for_ticket(title: str, summary: str = "") -> dict:
    """
    Core TSG search function - returns the most relevant TSG based on ticket info
    
    Args:
        title: Ticket title
        summary: Ticket summary/description (optional)
        
    Returns:
        dict: Single TSG result with highest confidence, or None if no results
    """
    try:
        store = get_tsg_store()
        
        # Combine title and summary for search query
        search_query = f"{title} {summary}".strip()
        
        if not search_query:
            return None
        
        # Preprocess if query is long (>500 chars)
        if len(search_query) > 500:
            original_length = len(search_query)
            search_query = preprocess_long_text(search_query)
            print(f"📝 Preprocessed text from {original_length} to {len(search_query)} characters")
        
        print(f"🔍 Searching TSG: {search_query[:200]}{'...' if len(search_query) > 200 else ''}")
        
        # Search for relevant TSGs (get top 3 for comparison, return best one)
        tsg_results = store.query(search_query, k=3)
        
        if not tsg_results:
            print("❌ No TSG results found")
            return None
        
        # Get the best result (first one has highest similarity)
        best_result = tsg_results[0]
        similarity_score = 1 - best_result.get('score', 1.0)  # Convert distance to similarity
        tsg_path = best_result.get('path', '')
        solution_content = extract_solution_from_tsg(tsg_path) if tsg_path else ""
        
        best_tsg = {
            "id": best_result.get('id'),
            "title": best_result.get('title'),
            "path": tsg_path,
            "similarity": similarity_score,
            "solution": solution_content
        }
        
        similarity_percent = similarity_score * 100
        print(f"✅ Found best matching TSG: {best_tsg.get('title')} (Similarity: {similarity_percent:.1f}%)")
        return best_tsg
            
    except Exception as e:
        print(f"❌ Error searching TSG: {e}")
        return None

def preprocess_long_text(text: str, max_length: int = 2000) -> str:
    """
    Preprocess long text for better embedding results
    
    Args:
        text: Input text to preprocess
        max_length: Maximum character length to keep
        
    Returns:
        str: Preprocessed text optimized for embedding
    """
    if not text or len(text) <= max_length:
        return text
    
    # Extract key information patterns
    key_patterns = []
    
    # 1. Extract error messages and exceptions
    import re
    error_patterns = [
        r'Exception: ([^\n]+)',
        r'Error: ([^\n]+)', 
        r'Failed: ([^\n]+)',
        r'(?:System\.\w+\.)*\w*Exception[^\n]*',
        r'at [^\n]+\.cs:line \d+',
        r'The SSL connection could not be established[^\n]*',
        r'certificate is invalid[^\n]*',
        r'NotTimeValid[^\n]*'
    ]
    
    for pattern in error_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        key_patterns.extend(matches[:3])  # Limit to 3 matches per pattern
    
    # 2. Extract first few lines (usually contain problem description)
    lines = text.split('\n')
    first_lines = [line.strip() for line in lines[:5] if line.strip()]
    
    # 3. Extract service/component names
    service_patterns = [
        r'(\w+Service)',
        r'(\w+Client)', 
        r'(\w+Processor)',
        r'(AP\w+)',
        r'(Scope\w+)',
        r'(Azure\w+)',
        r'(Microsoft\.\w+(?:\.\w+)*)'
    ]
    
    services = []
    for pattern in service_patterns:
        matches = re.findall(pattern, text)
        services.extend(matches[:2])  # Limit to 2 matches per pattern
    
    # 4. Combine key information
    processed_parts = []
    
    # Add first lines (problem description)
    if first_lines:
        processed_parts.extend(first_lines)
    
    # Add key error messages
    if key_patterns:
        processed_parts.append("Key errors: " + "; ".join(set(key_patterns[:5])))
    
    # Add service names
    if services:
        processed_parts.append("Services: " + ", ".join(set(services[:5])))
    
    # Join and truncate if still too long
    processed_text = " | ".join(processed_parts)
    
    if len(processed_text) > max_length:
        processed_text = processed_text[:max_length] + "..."
    
    return processed_text

# Simplified interface for testing - can be used by test files
def search_tsg_by_text(search_text: str, k: int = 3) -> list:
    """
    Simple text search interface for testing
    
    Args:
        search_text: Text to search for
        k: Number of results to return
        
    Returns:
        list: List of TSG results
    """
    return search_tsg_for_ticket(search_text, "", k)

if __name__ == "__main__":
    store = TSGVectorStore(tsg_root=os.path.join(os.path.dirname(__file__), '..', 'data', 'tsgs'))
    added = store.incremental_import()
    print(f"Added {added} tsgs to index")
