-- Inicialización de PostgreSQL con extensión pgvector para Aulento
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabla de embeddings vectoriales de conocimiento
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL, -- 'obsidian_note', 'book_page', 'fsrs_card', 'roadmap_topic'
    source_id VARCHAR(255) NOT NULL,
    source_title TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(768) NOT NULL, -- 768 dimensiones, del modelo que dice embedding_model
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índice HNSW para búsqueda por similitud de coseno ultrarrápida
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_cosine 
ON knowledge_embeddings USING hnsw (embedding vector_cosine_ops);

-- Índice para filtrado por tipo de fuente
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_source_type
ON knowledge_embeddings(source_type);

-- Cuenta dueña de cada fragmento: buscar, contar y borrar se filtran por ella
ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS user_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_user_id
ON knowledge_embeddings(user_id);

-- Modelo de embeddings con que se calculó cada vector: la búsqueda solo compara vectores del mismo modelo.
-- Una fila sin modelo es anterior a esta columna y se toma como de gemini-embedding-001.
ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_embedding_model
ON knowledge_embeddings(embedding_model);
