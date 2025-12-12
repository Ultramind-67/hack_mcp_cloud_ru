import os
import httpx
import chromadb
import uuid
import json
from mcp_server.mcp_instance import mcp
from mcp_server.utils import _require_env_vars

# --- НАСТРОЙКИ ---
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "project_docs"

# Инициализация ChromaDB
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)


# --- ФУНКЦИИ API CLOUD.RU (QWEN) ---

async def _get_embedding(text: str, api_key: str) -> list[float]:
    """Получает вектор через Qwen/Qwen3-Embedding-0.6B"""
    url = "https://foundation-models.api.cloud.ru/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": "Qwen/Qwen3-Embedding-0.6B", "input": [text]}

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
        if resp.status_code != 200:
            raise Exception(f"Embedding API Error {resp.status_code}: {resp.text}")
        return resp.json()["data"][0]["embedding"]


async def _rerank_documents(query: str, documents: list[str], api_key: str) -> list[str]:
    """Сортирует документы через Qwen/Qwen3-Reranker-0.6B"""
    url = "https://foundation-models.api.cloud.ru/score"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "Qwen/Qwen3-Reranker-0.6B",
        "encoding_format": "float",
        "text_1": query,
        "text_2": documents
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code != 200:
                print(f"⚠️ Ошибка реранкера {resp.status_code}: {resp.text}")
                return documents

            result_json = resp.json()
            data = result_json.get("data", [])
            data.sort(key=lambda x: x["score"], reverse=True)

            ranked_docs = []
            for item in data:
                if item["index"] < len(documents):
                    ranked_docs.append(documents[item["index"]])
            return ranked_docs
    except Exception as e:
        print(f"⚠️ Исключение в реранкере: {e}")
        return documents


# ==========================================
# ВНУТРЕННЯЯ ЛОГИКА (Для вызова из кода)
# ==========================================

async def _index_document_logic(filepath: str) -> str:
    """Логика индексации файла"""
    env = _require_env_vars(["API_KEY"])

    if not os.path.exists(filepath):
        return f"❌ Файл {filepath} не найден."

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()

        chunk_size = 1500
        overlap = 200
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunks.append(text[i:i + chunk_size])

        ids = []
        embeddings = []
        metadatas = []
        documents_list = []

        print(f"🔄 Индексация {filepath}: {len(chunks)} частей...")

        for i, chunk in enumerate(chunks):
            vector = await _get_embedding(chunk, env["API_KEY"])
            chunk_id = f"{os.path.basename(filepath)}_{i}_{str(uuid.uuid4())[:4]}"

            ids.append(chunk_id)
            embeddings.append(vector)
            documents_list.append(chunk)
            metadatas.append({"source": filepath, "chunk_index": i})

        if ids:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents_list,
                metadatas=metadatas
            )

        return f"✅ Файл {filepath} успешно проиндексирован! ({len(chunks)} фрагментов)."
    except Exception as e:
        return f"❌ Ошибка индексации: {str(e)}"


async def _search_knowledge_base_logic(query: str) -> str:
    """Логика поиска"""
    env = _require_env_vars(["API_KEY"])

    try:
        query_vec = await _get_embedding(query, env["API_KEY"])

        results = collection.query(query_embeddings=[query_vec], n_results=10)

        if not results["documents"] or not results["documents"][0]:
            return "📭 В базе знаний ничего не найдено."

        candidates = results["documents"][0]

        print(f"🔎 Реранкинг {len(candidates)} документов...")
        sorted_docs = await _rerank_documents(query, candidates, env["API_KEY"])
        final_docs = sorted_docs[:3]

        context = f"📚 **Найдено в базе знаний по запросу** '{query}':\n\n"
        for i, doc in enumerate(final_docs, 1):
            context += f"--- 📄 Фрагмент {i} ---\n{doc.strip()}\n\n"

        return context
    except Exception as e:
        return f"❌ Ошибка RAG поиска: {str(e)}"


# ==========================================
# MCP ИНСТРУМЕНТЫ (Для вызова Агентом)
# ==========================================

@mcp.tool(description="Индексирует (читает и запоминает) локальный файл в RAG. Args: filepath.")
async def index_document(filepath: str) -> str:
    return await _index_document_logic(filepath)


@mcp.tool(description="Умный поиск по документации/файлам (RAG) с реранкингом. Args: query.")
async def search_knowledge_base(query: str) -> str:
    return await _search_knowledge_base_logic(query)