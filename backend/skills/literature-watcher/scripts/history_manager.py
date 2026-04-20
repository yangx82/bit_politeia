import sqlite3
import os
import hashlib
from datetime import datetime
from pathlib import Path

class HistoryManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Default to backend/data/watcher_history.db
            # Relative to this script: ../../../../data/watcher_history.db
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            data_dir = base_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "watcher_history.db"
        else:
            self.db_path = Path(db_path)
            
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_id TEXT,
                    doi TEXT,
                    title TEXT COLLATE NOCASE,
                    abstract_hash TEXT,
                    published_date TEXT,
                    first_seen_at TEXT,
                    topic TEXT
                )
            ''')
            # Indexes for faster lookups
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_doi ON papers(doi)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_title ON papers(title)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ext_id ON papers(external_id)')
            conn.commit()

    def _get_hash(self, text):
        if not text:
            return ""
        return hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()

    def is_duplicate(self, doi=None, title=None, abstract=None, external_id=None):
        """Checks if a paper already exists in the history."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Check DOI
            if doi:
                cursor.execute('SELECT id FROM papers WHERE doi = ?', (doi.lower().strip(),))
                if cursor.fetchone():
                    return True
            
            # 2. Check External ID
            if external_id:
                cursor.execute('SELECT id FROM papers WHERE external_id = ?', (external_id,))
                if cursor.fetchone():
                    return True
            
            # 3. Check Title (Fuzzy-ish via NOCASE)
            if title:
                cursor.execute('SELECT id FROM papers WHERE title = ?', (title.strip(),))
                if cursor.fetchone():
                    return True
                    
            # 4. Check Abstract Hash
            if abstract:
                a_hash = self._get_hash(abstract)
                cursor.execute('SELECT id FROM papers WHERE abstract_hash = ?', (a_hash,))
                if cursor.fetchone():
                    return True
                    
        return False

    def add_paper(self, paper_data):
        """Adds a new paper to the history."""
        doi = paper_data.get('doi', '').lower().strip()
        title = paper_data.get('title', '').strip()
        abstract = paper_data.get('abstract', '')
        ext_id = paper_data.get('id', '')
        pub_date = paper_data.get('publication_date', '')
        topic = paper_data.get('topic', '')
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO papers (external_id, doi, title, abstract_hash, published_date, first_seen_at, topic)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                ext_id,
                doi,
                title,
                self._get_hash(abstract),
                pub_date,
                datetime.now().isoformat(),
                topic
            ))
            conn.commit()

if __name__ == "__main__":
    # Internal test
    manager = HistoryManager()
    test_paper = {
        'id': 'test-123',
        'doi': '10.1234/test.doi',
        'title': 'Test Paper Title',
        'abstract': 'This is a test abstract.',
        'publication_date': '2024-01-01',
        'topic': 'testing'
    }
    
    print(f"Is duplicate before add: {manager.is_duplicate(doi=test_paper['doi'])}")
    manager.add_paper(test_paper)
    print(f"Is duplicate after add: {manager.is_duplicate(doi=test_paper['doi'])}")
