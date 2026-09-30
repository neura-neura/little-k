import pytest
from dataclasses import replace
from app.storage import Storage
from app.config import Config

def test_identity_filters():
    c=Config.load()
    assert c.owner!=c.identity
    assert c.allowed(c.owner,c.owner,True)
    other=55555;c=replace(c,private_users=frozenset({other}))
    assert c.allowed(other,other,True)
    assert not c.allowed(777,777,True)
    assert not c.allowed(c.owner,c.identity,True)
    assert not c.allowed(c.owner,c.owner,True,outgoing=True)
    assert c.allowed(next(iter(c.chats)),other,False)
    assert not c.allowed(-99999,c.owner,False)

def test_sessions_persist_and_isolate(tmp_path):
    p=tmp_path/'state.db';s=Storage(p)
    a=s.session(1,0);assert s.session(1,0)==a
    assert s.session(2,0)!=a and s.session(1,99)!=a
    s.close();s=Storage(p);assert s.session(1,0)==a
    s.reset(1,0);assert s.session(1,0)!=a;s.close()

def test_dedup_recovery_no_replay(tmp_path):
    p=tmp_path/'state.db';s=Storage(p)
    assert s.claim('a') and not s.claim('a')
    s.voice('v',-100,10,'playing');s.close();s=Storage(p)
    assert not s.claim('a')
    assert s.db.execute('SELECT status FROM voice_jobs').fetchone()[0]=='interrupted'
    s.close()

def test_translations_idempotent(tmp_path):
    s=Storage(tmp_path/'db');s.generated(1,2,'hola','es')
    s.translation(1,2,'en','hello');s.translation(1,2,'en','hello')
    assert s.message(1,2)['translations']=={'en':'hello'}
    assert s.message(1,2)['original']=='hola';s.close()
