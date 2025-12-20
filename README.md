[![Ru](https://img.shields.io/badge/lang-ru-green.svg)](README.ru.md)
# 🏢 AI Procurement Agent (MCP-based Architecture)

[![Hackathon Winner](https://img.shields.io/badge/Award-3rd_Place_Cloud.ru_Hackathon-orange)](https://cloud.ru)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Architecture](https://img.shields.io/badge/Architecture-Model_Context_Protocol-purple)](https://modelcontextprotocol.io/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED)](https://www.docker.com/)

> **An autonomous multi-agent system designed to automate the procurement supply chain.**  
> Built using the **Model Context Protocol (MCP)**, this agent integrates Large Language Models (LLMs) with legacy enterprise APIs (SOAP), real-time web search, and a persistent RAG memory system.

---

## 🚀 Project Overview

This project was developed during the Cloud.ru Hackathon (3rd Place Winner). It solves a complex business problem: automating the interaction with suppliers, calculating logistics, and managing procurement data.

Unlike standard chatbots, this agent operates on a **Client-Server architecture** using the **Model Context Protocol (MCP)** by Anthropic. This allows the LLM to securely call external tools, execute code, and maintain state across sessions.

### Key Features
*   **🤖 Custom ReAct Loop:** Implemented a manual "Reasoning + Acting" loop (bypassing high-level abstractions like LangChain) for granular control over the agent's decision-making process.
*   **🧠 Hybrid RAG System:** Utilizes **ChromaDB** for vector storage and **Qwen-Reranker** to filter retrieved documents, ensuring high relevance of context.
*   **🔌 Legacy API Integration:** Seamlessly integrates with **DPD Logistics SOAP API**, handling raw XML construction and parsing within a modern Python async environment.
*   **📂 File-System Persistence:** The agent maintains "dossiers" on suppliers in Markdown format, automatically indexing them into its knowledge base.
*   **🌐 Real-time Web Intelligence:** Performs Google Search and parses website content (using Jina AI) to extract pricing and product data.

---

## 🛠 Technical Architecture

The system is split into two main components following the MCP standard:

### 1. The Agent (Client)
*   **Core Logic:** `agent/core.py` implements the ReAct loop. It parses the LLM's thought process, detects action triggers, and sends requests to the MCP Server.
*   **Interface:** A Streamlit-based dashboard for user interaction.
*   **LLM:** Integrated with **Qwen-2.5-Instruct** (via Cloud.ru API) and OpenAI-compatible endpoints.

### 2. The MCP Server (Tools)
*   **Framework:** Built with `FastMCP`. Exposes tools as standardized endpoints.
*   **Tools Implemented:**
    *   `dpd_calculator`: Logistics cost calculation (SOAP/XML).
    *   `rag_tools`: Embedding generation and Reranking logic.
    *   `web_search` & `jina_reader`: Internet data mining.
    *   `send_email`: SMTP/IMAP client for supplier communication.

![Architecture Diagram](architecture_diagram.png)

---

## 💻 Installation & Setup

The project is fully containerized.

### Prerequisites
*   Docker & Docker Compose
*   API Keys (Cloud.ru / OpenAI, Google Search, DPD credentials)

### 1. Clone the repository
```bash
git clone https://github.com/stavrmoris/hack_mcp_cloud_ru.git
cd hack_mcp_cloud_ru
```

### 2. Configure Environment
Create a `.env` file in the root directory:
```ini
API_KEY=your_llm_api_key
GOOGLE_API_KEY=your_google_key
GOOGLE_CSE_ID=your_cse_id
DPD_CLIENT_NUMBER=your_dpd_login
DPD_CLIENT_KEY=your_dpd_key
# See .env.example for full list
```

### 3. Run via Docker
```bash
docker build -t mcp-agent .
docker run -p 8501:8501 --env-file .env mcp-agent
```
Access the dashboard at `http://localhost:8501`

---

## 🧠 Deep Dive: Engineering Highlights

### Manual ReAct Implementation
Instead of relying on "black box" frameworks, I implemented the agentic loop manually in `agent/core.py`. This allows for:
*   Robust error handling when the LLM hallucinates arguments.
*   Support for multiple tool calling formats (XML, JSON, raw text).
*   Full observability of the "Thought -> Action -> Observation" chain.

### Integration with Legacy Systems (SOAP)
Many enterprise systems still rely on SOAP. This agent bridges the gap between modern JSON-based LLMs and XML-based SOAP services.
*   **File:** `mcp_server/tools/dpd_calculator.py`
*   **Logic:** Manually constructs SOAP Envelopes, handles XML namespaces, and parses responses into structured JSON for the Agent.

### Advanced RAG (Retrieval-Augmented Generation)
To avoid context pollution, the system uses a two-stage retrieval process:
1.  **Retrieval:** Fetch top-10 chunks from ChromaDB using cosine similarity.
2.  **Reranking:** Re-score these chunks using a Cross-Encoder model (`Qwen-Reranker`) to select the top-3 most semantically relevant contexts.

---

## 📂 Project Structure

```text
├── agent/                  # Client-side Logic
│   ├── core.py             # Custom ReAct Loop Implementation
│   ├── bot.py              # Telegram Bot Interface
│   └── main.py             # CLI Runner
├── mcp_server/             # Server-side Tools (FastMCP)
│   ├── server.py           # Entry point
│   └── tools/
│       ├── dpd_calculator.py # SOAP API wrapper
│       ├── rag_tools.py      # Vector DB & Reranking
│       ├── web_search.py     # Google Custom Search
│       └── suppliers.py      # Business logic
├── suppliers/              # Generated markdown dossiers (Persistent Memory)
├── Dockerfile              # Container config
└── app.py                  # Streamlit Dashboard
```

---

## 🏆 Acknowledgments
*   **Cloud.ru** for providing the LLM infrastructure and hosting the Hackathon.
*   **Anthropic** for the Model Context Protocol specification.