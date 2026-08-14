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
