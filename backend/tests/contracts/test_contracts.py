import json
from pathlib import Path

from api.app.schemas.errors import ErrorEnvelope
from api.app.schemas.identity import IdentityResponse
from api.app.schemas.jobs import JobResponse


FIXTURES = Path(__file__).parents[2] / "contracts" / "fixtures"


def assert_fixture_round_trips(name, model_type):
    payload = json.loads((FIXTURES / name).read_text())
    model = model_type.model_validate(payload)

    assert model.model_dump(mode="json", by_alias=True) == payload


def test_identity_fixture_round_trips():
    assert_fixture_round_trips("identity.json", IdentityResponse)


def test_job_fixture_round_trips():
    assert_fixture_round_trips("job.json", JobResponse)


def test_error_fixture_round_trips():
    assert_fixture_round_trips("error.json", ErrorEnvelope)
