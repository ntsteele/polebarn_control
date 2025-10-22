from __future__ import annotations

from pathlib import Path

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from core import xair_client
from web_control import app


@pytest.fixture
def client():
    return app.test_client()


def test_calibration_page_cards(client):
    resp = client.get('/calibration')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'Quick Gain Trim' in body
    assert 'Deep Venue' in body
    assert 'EQ Adjust / Presets' in body


def test_eq_current_shape(client):
    resp = client.get('/api/eq/current')
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {'lr', 'rear', 'sub'}
    for key in ('lr', 'rear', 'sub'):
        assert 'bands' in data[key]


def test_eq_apply_dry_run(client):
    before = xair_client.get_all_eq()
    payload = {
        'filters': {
            'lr': {
                'bands': [
                    {'type': 'peaking', 'freq': 1000.0, 'gain': 1.5, 'q': 1.1},
                ]
            }
        },
        'confirmation': 'APPLY',
    }
    resp = client.post('/api/eq/apply?dry_run=1', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['dry_run'] is True
    after = xair_client.get_all_eq()
    assert before == after


def test_rollback_without_snapshot(client):
    last_snapshot = Path('snapshots/LAST.json')
    if last_snapshot.exists():
        last_snapshot.unlink()
    resp = client.post('/api/eq/rollback')
    assert resp.status_code == 409
    data = resp.get_json()
    assert 'No snapshot' in data['err']
