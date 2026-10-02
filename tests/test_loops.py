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
        "poll_delay_s": 0.0,
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


def test_export_engine_nested_actions_preserves_engine_context_and_progress():
    dummy_manager = object()
    dummy_extractor = object()

    skill_def = {
        "id": "nested_ctx_skill",
        "name": "Nested Context Skill",
        "type": "export",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "loop_step",
                        "action_type": "FOR_EACH",
                        "collection_var": "items",
                        "item_var": "item",
                        "actions": [
                            {
                                "id": "inner_set",
                                "action_type": "SET_VARIABLE",
                                "variable": "seen_{item}",
                                "value": "yes",
                            }
                        ],
                    },
                    {"id": "final_step", "action_type": "SET_VARIABLE", "variable": "done", "value": "true"},
                ],
            }
        ],
    }

    engine = ExportEngine(
        skill_def,
        skill_manager=dummy_manager,
        vision_extractor=dummy_extractor,
    )

    progress_reports = []

    def reporter(p):
        progress_reports.append(p)

    context = {"items": ["alpha", "beta"]}
    success = engine.execute_actions(context=context, reporter=reporter)

    assert success is True
    assert context["seen_alpha"] == "yes"
    assert context["seen_beta"] == "yes"
    assert context["done"] == "true"
    assert engine.id == "nested_ctx_skill"
    assert engine.skill_manager is dummy_manager
    assert engine.vision_extractor is dummy_extractor

    # Verify that only the root completion emits a final "Completed" message,
    # nested loop actions must NOT emit premature "Completed ... (Nested)" messages
    completed_reports = [p for p in progress_reports if p.message.startswith("Completed")]
    assert len(completed_reports) == 1
    assert completed_reports[0].message == "Completed Nested Context Skill"
    assert completed_reports[0].percent == 100.0

