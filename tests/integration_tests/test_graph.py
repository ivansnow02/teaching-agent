import pytest

from agent import swarm

pytestmark = pytest.mark.anyio


@pytest.mark.langsmith
async def test_agent_simple_passthrough() -> None:
    inputs = {"changeme": "some_val"}
    res = await swarm.ainvoke(inputs)
    assert res is not None
