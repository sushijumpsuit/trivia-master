import json
from types import SimpleNamespace as NS

import pytest

from llm import LLMError, Message, ToolCall, ToolSpec
from llm.anthropic_llm import AnthropicLLM, to_anthropic_messages, to_anthropic_tools
from llm.openai_compat import OpenAICompatLLM, from_openai_response, to_openai_messages, to_openai_tools

SPEC = ToolSpec("update_score", "Record result", {"type": "object", "properties": {"correct": {"type": "boolean"}}})
HISTORY = [
    Message("user", "hi"),
    Message("assistant", "", [ToolCall("t1", "check_answer", {"player_answer": "KL"}),
                              ToolCall("t2", "update_score", {"correct": True})]),
    Message("tool", '{"expected_answer": "Kuala Lumpur"}', tool_call_id="t1"),
    Message("tool", '{"score": 1}', tool_call_id="t2"),
]


# ---------- OpenAI-compatible ----------

def test_openai_tools_are_wrapped_as_functions():
    assert to_openai_tools([SPEC])[0] == {"type": "function", "function": {
        "name": "update_score", "description": "Record result", "parameters": SPEC.parameters}}


def test_openai_messages_system_first_and_arguments_as_json_string():
    out = to_openai_messages("sys", HISTORY)
    assert out[0] == {"role": "system", "content": "sys"}
    call = out[2]["tool_calls"][0]
    assert json.loads(call["function"]["arguments"]) == {"player_answer": "KL"}
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": '{"expected_answer": "Kuala Lumpur"}'}


def openai_resp(content=None, calls=()):
    tcs = [NS(id=i, function=NS(name=n, arguments=a)) for i, n, a in calls]
    return NS(choices=[NS(message=NS(content=content, tool_calls=tcs or None))],
              usage=NS(prompt_tokens=10, completion_tokens=5))


def test_openai_response_parses_tool_calls():
    r = from_openai_response(openai_resp(None, [("c9", "update_score", '{"correct": true}')]))
    assert r.tool_calls == [ToolCall("c9", "update_score", {"correct": True})] and r.text == ""


def test_openai_bad_json_arguments_raise_llm_error():
    with pytest.raises(LLMError):
        from_openai_response(openai_resp(None, [("c9", "update_score", "{not json")]))


def test_openai_uses_right_token_param_per_provider():
    sent = {}
    client = NS(chat=NS(completions=NS(create=lambda **kw: sent.update(kw) or openai_resp("hey"))))
    OpenAICompatLLM("groq", "k", "m", client=client).chat("s", [Message("user", "x")], [SPEC])
    assert "max_completion_tokens" in sent and "tools" in sent
    sent.clear()
    OpenAICompatLLM("gemini", "k", "m", client=client).chat("s", [Message("user", "x")], [])
    assert "max_tokens" in sent and "tools" not in sent


def test_openai_sdk_errors_become_llm_error():
    def boom(**kw):
        raise RuntimeError("rate limited")
    client = NS(chat=NS(completions=NS(create=boom)))
    with pytest.raises(LLMError):
        OpenAICompatLLM("groq", "k", "m", client=client).chat("s", [Message("user", "x")], [])


# ---------- Anthropic ----------

def test_anthropic_tools_use_input_schema():
    assert to_anthropic_tools([SPEC])[0]["input_schema"] == SPEC.parameters


def test_anthropic_groups_consecutive_tool_results_into_one_user_message():
    out = to_anthropic_messages(HISTORY)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["t1", "t2"]
    assert out[1]["content"][0] == {"type": "tool_use", "id": "t1", "name": "check_answer", "input": {"player_answer": "KL"}}


def test_anthropic_round_trip_with_fake_client():
    sent = {}
    resp = NS(content=[NS(type="text", text="Nice!"),
                       NS(type="tool_use", id="tu1", name="update_score", input={"correct": True})],
              usage=NS(input_tokens=20, output_tokens=8))
    client = NS(messages=NS(create=lambda **kw: sent.update(kw) or resp))
    r = AnthropicLLM("k", "claude-x", client=client).chat("sys", HISTORY, [SPEC], max_tokens=300)
    assert sent["system"] == "sys" and sent["max_tokens"] == 300
    assert r.text == "Nice!" and r.tool_calls == [ToolCall("tu1", "update_score", {"correct": True})]


# ---------- DeepSeek (OpenAI-compatible, with optional thinking mode) ----------

def capture_client(resp):
    sent = {}
    return sent, NS(chat=NS(completions=NS(create=lambda **kw: sent.update(kw) or resp)))


def test_deepseek_uses_max_tokens_and_sends_thinking_setting():
    sent, client = capture_client(openai_resp("hi"))
    llm = OpenAICompatLLM("deepseek", "k", "deepseek-flash", client=client,
                          extra_body={"thinking": {"type": "disabled"}})
    llm.chat("s", [Message("user", "x")], [SPEC], max_tokens=200)
    assert sent["max_tokens"] == 200 and "max_completion_tokens" not in sent
    assert sent["extra_body"] == {"thinking": {"type": "disabled"}}


def test_reasoning_is_read_from_the_response():
    resp = openai_resp("done")
    resp.choices[0].message.reasoning_content = "The player said KL, which means Kuala Lumpur."
    assert from_openai_response(resp).reasoning.startswith("The player said KL")


def test_reasoning_is_sent_back_only_when_enabled():
    history = [Message("user", "hi"),
               Message("assistant", "", [ToolCall("t1", "update_score", {"correct": True})], reasoning="thinking..."),
               Message("tool", '{"score": 1}', tool_call_id="t1")]
    assert to_openai_messages("s", history, include_reasoning=True)[2]["reasoning_content"] == "thinking..."
    assert "reasoning_content" not in to_openai_messages("s", history)[2]


def test_factory_builds_deepseek_with_thinking_off_by_default(monkeypatch):
    import llm as llm_pkg
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "x" * 30)
    monkeypatch.delenv("DEEPSEEK_THINKING", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    assert llm_pkg.provider_settings()[2:] == ("deepseek-flash", "https://api.deepseek.com")
    assert llm_pkg.deepseek_options() == ({"thinking": {"type": "disabled"}}, False)
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    assert llm_pkg.deepseek_options() == ({"thinking": {"type": "enabled"}}, True)
    monkeypatch.setenv("DEEPSEEK_THINKING", "maybe")
    with pytest.raises(llm_pkg.LLMConfigError):
        llm_pkg.deepseek_options()



def test_anthropic_merges_player_message_after_tool_results():
    """Turns now end on tool results, so the next player message must join that user message."""
    history = HISTORY + [Message("user", "<player_answer>KL</player_answer>")]
    out = to_anthropic_messages(history)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[2]["content"][-1] == {"type": "text", "text": "<player_answer>KL</player_answer>"}
