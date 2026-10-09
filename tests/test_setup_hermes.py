from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from dotenv import dotenv_values
from scripts import setup_hermes


def test_profile_setup_is_local_and_preserves_existing_settings(tmp_path,monkeypatch,capsys):
    project=tmp_path/'project';project.mkdir()
    home=tmp_path/'hermes';home.mkdir()
    (home/'config.yaml').write_text('model: existing-model\n')
    (home/'.env').write_text('PROVIDER_KEY=private-provider-secret\nAPI_SERVER_PORT=8642\n')
    profile=home/'profiles/little-k-companion';profile.mkdir(parents=True)
    (profile/'config.yaml').write_text('model: existing-profile-model\n')
    (profile/'SOUL.md').write_text('existing personality')
    (project/'.env').write_text('HERMES_PROFILE=little-k-companion\n')
    monkeypatch.setattr(setup_hermes,'ROOT',project)
    monkeypatch.setenv('HERMES_HOME',str(home))
    monkeypatch.setenv('HERMES_CLI','fake-hermes')
    command=Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(setup_hermes.subprocess,'run',command)
    setup_hermes.main()
    assert (profile/'SOUL.md').read_text()=='existing personality'
    assert (profile/'config.yaml').read_text()=='model: existing-profile-model\n'
    root_values=dotenv_values(home/'.env')
    assert root_values['PROVIDER_KEY']=='private-provider-secret'
    assert root_values['API_SERVER_HOST']=='127.0.0.1'
    assert len(root_values['API_SERVER_KEY'])>=32
    assert root_values['API_SERVER_KEY']!=dotenv_values(profile/'.env')['API_SERVER_KEY']
    assert dotenv_values(project/'.env')['HERMES_KEY_FILE']==str(profile/'.env')
    assert (project/'data/hermes-env.before-setup').stat().st_mode&0o077==0
    assert 'private-provider-secret' not in capsys.readouterr().out
    command.assert_called_once_with(['fake-hermes','--profile','default','config','set','gateway.multiplex_profiles','true'],capture_output=True,text=True)


def test_setup_rejects_default_profile(tmp_path,monkeypatch):
    (tmp_path/'.env').write_text('HERMES_PROFILE=default\n')
    monkeypatch.setattr(setup_hermes,'ROOT',tmp_path)
    with pytest.raises(SystemExit,match='separate Hermes profile'):setup_hermes.main()
