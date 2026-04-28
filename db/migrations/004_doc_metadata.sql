-- Metadata de documentos para mejorar la búsqueda RAG.
-- Ejecutar en Supabase SQL editor tras 003_hybrid.sql.

alter table documents
  add column if not exists summary text,
  add column if not exists keywords text[] not null default '{}';

create index if not exists documents_keywords_gin_idx
  on documents using gin (keywords);
