from src.research_radar.models import ResearchField
from src.research_radar.ollama_field_planner import OllamaFieldPlanner, needs_field_planning


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.chat_payload = None

    def get(self, url, timeout):
        return FakeResponse({"models": [{"name": "llama3.2:latest"}, {"name": "qwen3:8b"}]})

    def post(self, url, json, timeout):
        self.chat_payload = json
        return FakeResponse(
            {
                "message": {
                    "content": '{"core_keywords":["multimodal recommendation","missing modality"],'
                    '"intent_queries":["recommendation systems robust to incomplete multimodal data"],'
                    '"optional_keywords":["modality imputation"]}'
                }
            }
        )


def field(**overrides):
    values = {"id": "field-1", "slug": "test", "name": "Incomplete Multimodal Recommendation"}
    values.update(overrides)
    return ResearchField(**values)


def test_qwen_plans_field_queries_as_json():
    session = FakeSession()
    plan = OllamaFieldPlanner(session=session).plan(field())
    assert plan["model"] == "qwen3:8b"
    assert plan["core_keywords"] == ["multimodal recommendation", "missing modality"]
    assert plan["intent_queries"] == ["recommendation systems robust to incomplete multimodal data"]
    assert session.chat_payload["think"] is False
    assert session.chat_payload["format"] == "json"
    assert session.chat_payload["keep_alive"] == "30m"


def test_planning_is_only_needed_for_empty_or_name_only_fields():
    assert needs_field_planning(field()) is True
    assert needs_field_planning(field(core_keywords=["Incomplete Multimodal Recommendation"])) is True
    assert needs_field_planning(field(core_keywords=["missing modality"])) is False
