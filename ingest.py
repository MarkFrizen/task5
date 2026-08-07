#!/usr/bin/env python3
"""Скрипт для загрузки документов, чанкинга и создания FAISS индекса."""

import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from config import config

def ingest_documents(data_dir: str, index_path: str):
    """Загружает все документы из папки и создаёт индекс."""
    if not os.path.exists(data_dir):
        print(f"Папка {data_dir} не найдена. Создаю...")
        os.makedirs(data_dir)
        print(f"Поместите ваши документы (.txt, .pdf) в {data_dir} и запустите скрипт снова.")
        return

    loaders = [
        DirectoryLoader(data_dir, glob="*.txt", loader_cls=TextLoader),
        DirectoryLoader(data_dir, glob="*.pdf", loader_cls=PyPDFLoader),
    ]
    docs = []
    for loader in loaders:
        try:
            docs.extend(loader.load())
        except Exception as e:
            print(f"Ошибка загрузки: {e}")

    if not docs:
        print("Документы не найдены. Поддерживаются .txt и .pdf.")
        return

    # Чанкинг
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    print(f"Создано {len(chunks)} чанков.")

    # Эмбеддинги
    embeddings = HuggingFaceEmbeddings(model_name=config.embedding_model)
    vector_store = FAISS.from_documents(chunks, embeddings)
    vector_store.save_local(index_path)
    print(f"Индекс сохранён в {index_path}")

if __name__ == "__main__":
    data_dir = "./data"
    index_path = config.index_path
    ingest_documents(data_dir, index_path)