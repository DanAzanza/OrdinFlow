"""Unit tests for FOR_EACH and WHILE_LOOP execution in OrdinFlow RPA."""

from core.skills.engines.export_engine import ExportEngine
from core.skills.loop_runner import (
    execute_for_each_collection,
    execute_while_loop,
)


def test_execute_for_each_collection_basic():
    collected: list[str] = []
    context = {"items": ["item_a", "item_b", "item_c"]}

    step = {
        "id": "loop_test",
        "action_type": "FOR_EACH",
        "collection_var": "items",
        "item_var": "curr",
        "actions": [{"id": "sub_act"}],
    }

    def dummy_executor(actions, ctx, depth):
        collected.append(f"{ctx['curr']}_{ctx['item_index']}")
        return True

    success = execute_for_each_collection(step, context, dummy_executor)
    assert success is True
    assert collected == ["item_a_1", "item_b_2", "item_c_3"]


def test_execute_for_each_collection_empty():
    context = {"items": []}
    step = {
        "id": "empty_loop",
        "action_type": "FOR_EACH",
        "collection_var": "items",
        "actions": [],
    }
    success = execute_for_each_collection(step, context, lambda a, c, d: True)
    assert success is True


def test_execute_while_loop_terminates_on_condition():
    context = {"counter": 0}
    step = {
        "id": "while_test",
        "action_type": "WHILE_LOOP",
        "condition": "{counter} < 3",
        "actions": [{"id": "sub_inc"}],
    }

    def dummy_executor(actions, ctx, depth):
        ctx["counter"] += 1
        return True

    success = execute_while_loop(step, context, dummy_executor)
    assert success is True
    assert context["counter"] == 3


def test_execute_while_loop_hits_max_iterations():
    context = {"infinite": True}
    step = {
        "id": "infinite_while",
        "action_type": "WHILE_LOOP",
        "condition": "True",
        "max_iterations": 10,
        "actions": [{"id": "sub_act"}],
    }
    iters = 0

    def dummy_executor(actions, ctx, depth):
        nonlocal iters
        iters += 1
        return True

    # When max iterations is reached without condition flipping, it terminates cleanly
    success = execute_while_loop(step, context, dummy_executor)
    assert success is True
    assert iters == 10


def test_export_engine_with_for_each_and_while_loops():
    skill_def = {
        "id": "loop_engine_skill",
        "name": "Loop Engine Skill",
        "type": "export",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {"id": "a_set", "action_type": "SET_VARIABLE", "variable": "counter", "value": "0"},
                    {
                        "id": "a_for_each",
                        "action_type": "FOR_EACH",
                        "collection_var": "tags",
                        "item_var": "tag",
                        "actions": [
                            {
                                "id": "sub_append",
                                "action_type": "SET_VARIABLE",
                                "variable": "last_tag",
                                "value": "{tag}",
                            }
                        ],
                    },
                ],
            }
        ],
    }

    engine = ExportEngine(skill_def)
    context = {"tags": ["tag1", "tag2", "tag3"]}
    success = engine.execute_actions(context=context)
    assert success is True
    assert context["last_tag"] == "tag3"
