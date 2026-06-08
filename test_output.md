# KẾT QUẢ THỰC THI KIỂM THỬ HỆ THỐNG (TEST EXECUTION OUTPUT)

Tài liệu này ghi nhận kết quả thực thi trực tiếp từ terminal khi chạy toàn bộ **38/38 ca kiểm thử** của hệ thống ở chế độ trực tuyến (Online Mode), bao gồm cả các ca kiểm thử mới được bổ sung cho cơ chế **Combat Stat** (Chỉ số chiến đấu).

---

## 💻 KẾT QUẢ IN RA TỪ TERMINAL (PYTEST OUTPUT)

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0 -- d:\D\HOCTAP\TDTT\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\D\HOCTAP\TDTT\AI-Adventure-Game
plugins: anyio-4.13.0, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 38 items

tests/integration/test_api.py::test_ping_endpoint PASSED                 [  2%]
tests/integration/test_api.py::test_check_config_endpoint_success PASSED [  5%]
tests/integration/test_api.py::test_check_config_endpoint_failure PASSED [  7%]
tests/integration/test_api.py::test_poll_updates_endpoint PASSED         [ 10%]
tests/integration/test_api.py::test_diary_endpoint PASSED                [ 13%]
tests/integration/test_api.py::test_inventory_equip_endpoint_not_found PASSED [ 15%]
tests/integration/test_database.py::test_database_manager_lifecycle PASSED [ 18%]
tests/integration/test_online_agents.py::test_online_intent_router_gemini PASSED [ 21%]
tests/integration/test_online_agents.py::test_online_choice_agent_groq PASSED [ 23%]
tests/integration/test_online_agents.py::test_online_music_classifier_gemini PASSED [ 26%]
tests/integration/test_online_agents.py::test_online_query_agent_groq PASSED [ 28%]
tests/unit/test_combat_mechanics.py::test_action_processor_build_combat_stats_directive_success PASSED [ 31%]
tests/unit/test_combat_mechanics.py::test_action_processor_build_combat_stats_directive_failure_with_weapon PASSED [ 34%]
tests/unit/test_combat_mechanics.py::test_combat_agent_extract_combat PASSED [ 36%]
tests/unit/test_combat_mechanics.py::test_state_processor_combat_integration PASSED [ 39%]
tests/unit/test_entities.py::test_base_entity_initialization PASSED      [ 42%]
tests/unit/test_entities.py::test_consumable_item_initialization PASSED  [ 44%]
tests/unit/test_entities.py::test_weapon_item_initialization PASSED      [ 47%]
tests/unit/test_entities.py::test_quest_item_initialization PASSED       [ 50%]
tests/unit/test_entities.py::test_miscellaneous_item_initialization PASSED [ 52%]
tests/unit/test_entities.py::test_quest_initialization PASSED            [ 55%]
tests/unit/test_entities.py::test_location_initialization PASSED         [ 57%]
tests/unit/test_entities.py::test_npc_initialization PASSED              [ 60%]
tests/unit/test_entities.py::test_memory_dataclass PASSED                [ 63%]
tests/unit/test_memory_processor.py::test_rerank_memories_time_decay_and_bonuses PASSED [ 65%]
tests/unit/test_player_state.py::test_player_state_initialization PASSED [ 68%]
tests/unit/test_player_state.py::test_player_state_clear PASSED          [ 71%]
tests/unit/test_player_state.py::test_player_take_damage_and_die PASSED  [ 73%]
tests/unit/test_player_state.py::test_equip_and_change_weapon PASSED     [ 76%]
tests/unit/test_player_state.py::test_use_consumables PASSED             [ 78%]
tests/unit/test_player_state.py::test_quest_management PASSED            [ 81%]
tests/unit/test_player_state.py::test_serialize_to_dict PASSED           [ 84%]
tests/unit/test_player_state.py::test_deserialize_load_state PASSED      [ 86%]
tests/unit/test_text_formatter.py::test_parse_story_with_tags PASSED     [ 89%]
tests/unit/test_text_formatter.py::test_parse_story_with_npc_talk_no_name PASSED [ 92%]
tests/unit/test_text_formatter.py::test_parse_story_fallback_with_quotes PASSED [ 94%]
tests/unit/test_text_formatter.py::test_parse_story_pure_narration PASSED [ 97%]
tests/unit/test_text_formatter.py::test_parse_story_empty_text PASSED    [100%]

============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

tests/integration/test_online_agents.py::test_online_intent_router_gemini
tests/integration/test_online_agents.py::test_online_music_classifier_gemini
  d:\D\HOCTAP\TDTT\.venv\Lib\site-packages\google\genai\_api_client.py:927: DeprecationWarning: Inheritance class AiohttpClientSession from ClientSession is discouraged
    class AiohttpClientSession(aiohttp.ClientSession):  # type: ignore[misc]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 38 passed, 5 warnings in 22.74s =======================
```
