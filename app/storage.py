import sqlite3
import json
import uuid
import time

class Storage:
    def __init__(self,path,recover=True):
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(path)
        path.chmod(0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS conversations(chat INTEGER,topic INTEGER,session TEXT,PRIMARY KEY(chat,topic));
        CREATE TABLE IF NOT EXISTS events(key TEXT PRIMARY KEY,status TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS messages(chat INTEGER,id INTEGER,original TEXT,language TEXT,translations TEXT,PRIMARY KEY(chat,id));
        CREATE TABLE IF NOT EXISTS voice_jobs(id TEXT PRIMARY KEY,chat INTEGER,message INTEGER,status TEXT,created REAL);
        ''');self.db.commit()
        # Never replay voice after a crash: prior playback may already have reached listeners.
        if recover:
            self.db.execute("UPDATE voice_jobs SET status='interrupted' WHERE status IN ('queued','playing')")
            self.db.execute("UPDATE events SET status='interrupted' WHERE status='processing'")
        self.db.commit()
    def claim(self,key):
        try:
            self.db.execute('INSERT INTO events VALUES (?,?,?)',(key,'processing',time.time()));self.db.commit();return True
        except sqlite3.IntegrityError:return False
    def finish(self,key,status='done'):
        self.db.execute('UPDATE events SET status=? WHERE key=?',(status,key));self.db.commit()
    def session(self,chat,topic):
        row=self.db.execute('SELECT session FROM conversations WHERE chat=? AND topic=?',(chat,topic)).fetchone()
        if row:return row[0]
        sid='littlek_'+uuid.uuid4().hex
        self.db.execute('INSERT INTO conversations VALUES (?,?,?)',(chat,topic,sid));self.db.commit();return sid
    def set_session(self,chat,topic,sid):
        self.db.execute('INSERT OR REPLACE INTO conversations VALUES (?,?,?)',(chat,topic,sid));self.db.commit()
    def reset(self,chat,topic):
        self.db.execute('DELETE FROM conversations WHERE chat=? AND topic=?',(chat,topic));self.db.commit()
    def generated(self,chat,mid,text,language):
        self.db.execute('INSERT OR REPLACE INTO messages VALUES (?,?,?,?,?)',(chat,mid,text,language,'{}'));self.db.commit()
    def message(self,chat,mid):
        row=self.db.execute('SELECT original,language,translations FROM messages WHERE chat=? AND id=?',(chat,mid)).fetchone()
        return {'original':row[0],'language':row[1],'translations':json.loads(row[2])} if row else None
    def translation(self,chat,mid,language,text):
        m=self.message(chat,mid);m['translations'][language]=text
        self.db.execute('UPDATE messages SET translations=? WHERE chat=? AND id=?',(json.dumps(m['translations'],ensure_ascii=False),chat,mid));self.db.commit()
    def voice(self,job,chat,mid,status):
        self.db.execute('INSERT INTO voice_jobs VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status',(job,chat,mid,status,time.time()));self.db.commit()
    def prune(self):
        # Keep IDs for idempotence; drop cached message content after 30 days via bounded row count.
        self.db.execute('DELETE FROM messages WHERE rowid NOT IN (SELECT rowid FROM messages ORDER BY rowid DESC LIMIT 1000)');self.db.commit()
    def setting(self,key,default=None):
        row=self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def set_setting(self,key,value):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
        self.db.commit()
    def close(self):self.db.close()
