"""Unit tests for qa_mcp.core.persistence - the state must survive a process
restart and must not corrupt other modules' data when multiple
PersistentStore instances (one per module) share the same file.
"""
from qa_mcp.core.persistence import PersistentStore


def test_namespace_round_trips_after_save(tmp_path):
    path = str(tmp_path / "state.json")
    store = PersistentStore(path)
    ns = store.namespace("defects")
    ns["d1"] = {"title": "bug"}
    store.save()

    reloaded = PersistentStore(path)
    assert reloaded.namespace("defects") == {"d1": {"title": "bug"}}


def test_state_survives_new_instance_simulating_process_restart(tmp_path):
    path = str(tmp_path / "state.json")

    first = PersistentStore(path)
    first.namespace("test_runs")["run-1"] = {"status": "passed"}
    first.save()
    del first

    second = PersistentStore(path)
    assert second.namespace("test_runs")["run-1"]["status"] == "passed"


def test_two_instances_owning_different_namespaces_do_not_clobber_each_other(tmp_path):
    path = str(tmp_path / "state.json")

    defects_store = PersistentStore(path)
    defects_store.namespace("defects")["d1"] = {"title": "bug"}
    defects_store.save()

    runs_store = PersistentStore(path)
    runs_store.namespace("test_runs")["run-1"] = {"status": "passed"}
    runs_store.save()

    final = PersistentStore(path)
    assert final.namespace("defects") == {"d1": {"title": "bug"}}
    assert final.namespace("test_runs") == {"run-1": {"status": "passed"}}


def test_corrupt_json_file_does_not_crash_on_load(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not valid json")

    store = PersistentStore(str(path))

    assert store.namespace("anything") == {}


def test_repeated_save_on_same_instance_keeps_writing_new_mutations(tmp_path):
    """Regression test: a caller that calls namespace() once (as every real
    module in this codebase does in __init__) and then mutates the returned
    dict across many separate save() calls must see every mutation land on
    disk - not just the first one. save() used to reassign self._data to a
    brand new dict on every call, which silently detached the reference
    namespace() had already handed out; the second save() onward wrote stale
    data and any new mutation was lost.
    """
    path = str(tmp_path / "state.json")
    store = PersistentStore(path)
    ns = store.namespace("test_runs")

    ns["run-1"] = {"total_tests": 0}
    store.save()

    ns["run-1"] = {"total_tests": 1}
    store.save()

    ns["run-1"] = {"total_tests": 2}
    store.save()

    reloaded = PersistentStore(path)
    assert reloaded.namespace("test_runs")["run-1"]["total_tests"] == 2
