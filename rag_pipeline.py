import os
import time
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from markitdown import MarkItDown
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import MarkdownTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

class KnowledgeBase:
    def __init__(self):
        self.raw_data_dir = "data"
        self.md_dir = "markdown_db"
        self.db_dir = "vector_db"
        
        os.makedirs(self.raw_data_dir, exist_ok=True)
        os.makedirs(self.md_dir, exist_ok=True)
        
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.vector_store = None
        self.md_converter = MarkItDown()

    def _convert_single_file(self, filename):
        """Worker function for multithreading."""
        if not filename.endswith('.html'): return
        
        input_path = os.path.join(self.raw_data_dir, filename)
        output_filename = f"{os.path.splitext(filename)[0]}.md"
        output_path = os.path.join(self.md_dir, output_filename)
        
        if not os.path.exists(output_path):
            try:
                # Convert using the native Python API (MUCH faster)
                result = self.md_converter.convert(input_path)
                
                # Inject the file name at the top as an H1 Header for better RAG
                content = f"# API Reference: {filename}\n\n{result.text_content}"
                
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                # Silently catch weirdly formatted HTML files so the loop doesn't crash
                pass 

    def convert_files_to_markdown_fast(self):
        """Uses multithreading to chew through 70k files quickly."""
        files = [f for f in os.listdir(self.raw_data_dir) if f.endswith('.html')]
        
        # Check how many are left to convert to avoid re-running
        existing_mds = set(os.listdir(self.md_dir))
        files_to_process = [f for f in files if f"{os.path.splitext(f)[0]}.md" not in existing_mds]

        if not files_to_process:
            print("All files are already converted to Markdown!")
            return

        print(f"Converting {len(files_to_process)} files to Markdown. This will take a few minutes...")
        
        # Use ThreadPoolExecutor to process 16 files at once
        with ThreadPoolExecutor(max_workers=16) as executor:
            list(tqdm(executor.map(self._convert_single_file, files_to_process), total=len(files_to_process)))

    def build_vector_db(self):
        """Loads and batches documents into ChromaDB safely."""
        self.convert_files_to_markdown_fast()
        
        print("Loading markdown files into database. Please wait...")
        # Use multithreading in Langchain loader to speed up disk reads
        loader = DirectoryLoader(self.md_dir, glob="**/*.md", loader_cls=TextLoader, use_multithreading=True)
        documents = loader.load()
        
        if not documents:
            print("No markdown files found. Database is empty.")
            return

        print(f"Loaded {len(documents)} documents. Splitting text...")
        splitter = MarkdownTextSplitter(chunk_size=1200, chunk_overlap=150)
        chunks = splitter.split_documents(documents)
        
        print(f"Storing {len(chunks)} chunks in ChromaDB (This might take a while for 70k files)...")
        # Chroma handles its own batching under the hood in newer versions
        self.vector_store = Chroma.from_documents(
            documents=chunks, 
            embedding=self.embeddings, 
            persist_directory=self.db_dir
        )
        print("Database built successfully!")

    def search(self, query, top_k=5):
        if not self.vector_store:
            self.vector_store = Chroma(persist_directory=self.db_dir, embedding_function=self.embeddings)
        results = self.vector_store.similarity_search(query, k=top_k)
        return "\n\n---\n\n".join([doc.page_content for doc in results])

if __name__ == "__main__":
    kb = KnowledgeBase()
    kb.build_vector_db()