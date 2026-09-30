import pytest
from types import SimpleNamespace
from app.parser import parse,split_text,topic_id

@pytest.mark.parametrize('text,lang', [('.t',None),('.T',None),('.t zh','zh'),('.T ZH','zh'),('.tzh','zh'),('.t.zh','zh'),('.tes','es'),('.t en','en')])
def test_translate_shortcuts(text,lang):
    p=parse(text);assert p.translate and p.language==lang and p.text==''
@pytest.mark.parametrize('text',['.c','.C'])
def test_call(text):assert parse(text).speak
@pytest.mark.parametrize('text',['.t zh .c pregunta','.c .t zh pregunta','.tzh .c pregunta','.t.zh .C pregunta'])
def test_combination(text):
    p=parse(text);assert p.text=='pregunta' and p.language=='zh' and p.translate and p.speak

def test_suffix():
    p=parse('Buenas noches amor .t zh');assert p.text=='Buenas noches amor' and p.language=='zh'
@pytest.mark.parametrize('text',['http://a.t','filename.txt','foo.c','Esto .cosa','Un .twrong texto'])
def test_no_false_shortcuts(text):
    p=parse(text);assert not p.translate and not p.speak and p.text==text

def test_natural_language_left_to_hermes():
    for t in ['traduce esto a chino: buenas noches','respóndeme en chino: ¿cuánto es 5+5?',
              'entra a la llamada y dime la respuesta','traduce tu respuesta a inglés y léela en la llamada','dilo en chino por la llamada']:
        assert parse(t).text==t

def test_unicode_splitting_lossless():
    text=('🐈 中文. Hola.\n\n'*1400)+'final'
    parts=list(split_text(text));assert ''.join(parts)==text
    assert all(len(x.encode('utf-16-le'))//2<=4000 for x in parts)

def test_topics():
    assert topic_id(SimpleNamespace(reply_to=None))==0
    assert topic_id(SimpleNamespace(reply_to=SimpleNamespace(forum_topic=False)))==0
    assert topic_id(SimpleNamespace(reply_to=SimpleNamespace(forum_topic=True,reply_to_top_id=99,reply_to_msg_id=123)))==99
