import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.models.tool_call import ToolCall
from app.llm.client import OllamaClient, ollama_client
from app.llm.prompt import build_system_prompt
from app.llm.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8


def parse_tool_calls_from_response(
    message_dict: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    """
    Model-agnostic tool call parser.
    Detects native OpenAI tool_calls or JSON block structures in text.
    Returns: (parsed_tool_calls, is_valid_json, error_message)
    """
    tool_calls = []
    
    # 1. Native OpenAI tool calls
    native_calls = message_dict.get("tool_calls")
    if native_calls and isinstance(native_calls, list):
        for idx, call in enumerate(native_calls):
            fn = call.get("function", {})
            name = fn.get("name")
            raw_args = fn.get("arguments", {})
            call_id = call.get("id") or f"call_{idx}_{name}"
            
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError as err:
                    return [], False, f"Malformed JSON in tool '{name}' arguments: {err}"
            else:
                args = {}

            tool_calls.append({
                "id": call_id,
                "name": name,
                "arguments": args
            })
        return tool_calls, True, None

    # 2. Text fallback: parse ```json ... ``` blocks or JSON objects in content
    content = message_dict.get("content") or ""
    if not content:
        return [], True, None

    # Search for markdown json blocks or standalone JSON
    json_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    candidates = json_blocks if json_blocks else [content]

    for candidate in candidates:
        candidate_str = candidate.strip()
        if not (candidate_str.startswith("{") or candidate_str.startswith("[")):
            continue

        try:
            data = json.loads(candidate_str)
            if isinstance(data, dict):
                if "tool" in data and "args" in data:
                    tool_calls.append({
                        "id": f"call_text_{data['tool']}",
                        "name": data["tool"],
                        "arguments": data.get("args") or {}
                    })
                elif "name" in data and ("arguments" in data or "parameters" in data):
                    tool_calls.append({
                        "id": f"call_text_{data['name']}",
                        "name": data["name"],
                        "arguments": data.get("arguments") or data.get("parameters") or {}
                    })
                elif "tool_calls" in data and isinstance(data["tool_calls"], list):
                    for tc in data["tool_calls"]:
                        if isinstance(tc, dict) and "name" in tc:
                            tool_calls.append({
                                "id": tc.get("id", f"call_text_{tc['name']}"),
                                "name": tc["name"],
                                "arguments": tc.get("arguments") or tc.get("args") or {}
                            })
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item:
                        tool_calls.append({
                            "id": item.get("id", f"call_text_{item['name']}"),
                            "name": item["name"],
                            "arguments": item.get("arguments") or item.get("args") or {}
                        })
        except json.JSONDecodeError:
            # Candidate looked like JSON but failed to parse
            if json_blocks:
                return [], False, f"Failed to parse tool call JSON block: '{candidate_str}'"

    return tool_calls, True, None


async def execute_single_tool(
    call: Dict[str, Any],
    db: Session,
    parent_message_id: Optional[str] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Execute a single tool, record execution metrics, and log to tool_calls DB table."""
    tool_name = call["name"]
    args = call["arguments"]
    call_id = call["id"]

    start_time = time.perf_counter()
    ok = True
    result_data: Any = None

    try:
        result_data = await tool_registry.execute_tool(tool_name, args, db=db)
    except Exception as err:
        ok = False
        result_data = {"error": str(err)}
        logger.error(f"Error executing tool '{tool_name}': {err}", exc_info=True)

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    args_json_str = json.dumps(args, ensure_ascii=False)
    result_json_str = json.dumps(result_data, ensure_ascii=False)

    # Log to tool_calls DB table
    db_tool_call = ToolCall(
        message_id=parent_message_id,
        tool_name=tool_name,
        args_json=args_json_str,
        result_json=result_json_str,
        ok=ok,
        duration_ms=duration_ms,
    )
    db.add(db_tool_call)
    db.commit()

    tool_msg = {
        "role": "tool",
        "tool_call_id": call_id,
        "name": tool_name,
        "content": result_json_str
    }
    return call, tool_msg


async def run_agent_loop(
    conversation_id: str,
    user_input: str,
    db: Session,
    extra_context: Optional[str] = None,
    client: Optional[OllamaClient] = None
) -> str:
    """
    Main agent execution loop:
    1. Ensure conversation exists & store user message.
    2. Build system prompt & prepare message history.
    3. Loop up to 8 iterations: chat completion -> detect tool calls -> parallel execute -> repeat.
    4. Save final assistant response & return content.
    """
    llm = client or ollama_client
    tool_registry.reload()

    # 1. Fetch or create conversation
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        conv = Conversation(id=conversation_id, title=user_input[:50])
        db.add(conv)
        db.commit()

    # 2. Store user message in DB
    user_msg_db = Message(
        conversation_id=conversation_id,
        role="user",
        content=user_input,
        token_count=OllamaClient.estimate_tokens(user_input)
    )
    db.add(user_msg_db)
    db.commit()
    db.refresh(user_msg_db)

    # 3. Load rolling conversation context & summary
    from app.services import memory as memory_service
    await memory_service.maybe_update_rolling_summary(db=db, conversation_id=conversation_id)
    ctx = memory_service.get_conversation_context(db=db, conversation_id=conversation_id)

    # 4. Recall relevant facts
    facts = memory_service.recall_facts(db=db, query=user_input)
    facts_summary = None
    if facts:
        facts_summary = "\n".join([f"- {f.subject} {f.predicate}: {f.value}" for f in facts])

    # 5. Build system prompt with rolling summary & facts
    combo_extra = []
    if ctx.get("summary"):
        combo_extra.append(f"Conversation Summary:\n{ctx['summary']}")
    if extra_context:
        combo_extra.append(extra_context)

    system_prompt = build_system_prompt(
        extra_context="\n\n".join(combo_extra) if combo_extra else None,
        facts_summary=facts_summary
    )

    messages_payload: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for msg in ctx.get("recent_messages", []):
        messages_payload.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    tool_schemas = tool_registry.get_schemas()
    retry_count = 0

    # 4. Agent loop iteration
    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info(f"Agent loop iteration {iteration}/{MAX_ITERATIONS}")
        
        response = await llm.chat_completion(
            messages=messages_payload,
            tools=tool_schemas if tool_schemas else None,
            stream=False
        )

        choices = response.get("choices", [])
        if not choices:
            final_text = "I apologize, but I received an empty response from the language model."
            break

        msg_obj = choices[0].get("message", {})
        tool_calls, is_valid_json, parse_err = parse_tool_calls_from_response(msg_obj)

        # Handle malformed tool call JSON retry once
        if not is_valid_json and retry_count < 1:
            retry_count += 1
            logger.warning(f"Malformed tool call JSON detected. Retrying iteration with error feedback: {parse_err}")
            messages_payload.append({
                "role": "assistant",
                "content": msg_obj.get("content") or ""
            })
            messages_payload.append({
                "role": "user",
                "content": f"[System Error] {parse_err}. Please format your tool call with valid JSON."
            })
            continue

        # If no tool calls, return final text content
        if not tool_calls:
            final_text = msg_obj.get("content") or ""
            break

        # Save assistant message requesting tool calls
        assistant_msg_db = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=msg_obj.get("content") or f"[Tool call requested: {[t['name'] for t in tool_calls]}]",
            token_count=OllamaClient.estimate_tokens(msg_obj.get("content") or "")
        )
        db.add(assistant_msg_db)
        db.commit()
        db.refresh(assistant_msg_db)

        # Append assistant message to context payload
        assistant_payload_entry: Dict[str, Any] = {
            "role": "assistant",
            "content": msg_obj.get("content")
        }
        if "tool_calls" in msg_obj:
            assistant_payload_entry["tool_calls"] = msg_obj["tool_calls"]
        messages_payload.append(assistant_payload_entry)

        # Run independent tool calls in parallel using asyncio.gather
        tasks = [
            execute_single_tool(call, db=db, parent_message_id=assistant_msg_db.id)
            for call in tool_calls
        ]
        results = await asyncio.gather(*tasks)

        for _, tool_msg in results:
            messages_payload.append(tool_msg)
    else:
        # If loop reached max iterations without ending
        final_text = messages_payload[-1].get("content") or "Reached maximum iteration limit for tool calls."

    # Save final assistant response message to DB
    final_msg_db = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=final_text,
        token_count=OllamaClient.estimate_tokens(final_text)
    )
    db.add(final_msg_db)
    db.commit()

    return final_text


async def stream_agent_loop(
    conversation_id: str,
    user_input: str,
    db: Session,
    extra_context: Optional[str] = None,
    client: Optional[OllamaClient] = None
):
    """
    Streaming generator for agent execution loop:
    Yields SSE events: tool_start, tool_result, token, done.
    """
    llm = client or ollama_client
    tool_registry.reload()

    # 1. Fetch or create conversation
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        conv = Conversation(id=conversation_id, title=user_input[:50])
        db.add(conv)
        db.commit()

    # 2. Store user message in DB
    user_msg_db = Message(
        conversation_id=conversation_id,
        role="user",
        content=user_input,
        token_count=OllamaClient.estimate_tokens(user_input)
    )
    db.add(user_msg_db)
    db.commit()
    db.refresh(user_msg_db)

    # 3. Load rolling conversation context & summary
    from app.services import memory as memory_service
    await memory_service.maybe_update_rolling_summary(db=db, conversation_id=conversation_id)
    ctx = memory_service.get_conversation_context(db=db, conversation_id=conversation_id)

    # 4. Recall relevant facts
    facts = memory_service.recall_facts(db=db, query=user_input)
    facts_summary = None
    if facts:
        facts_summary = "\n".join([f"- {f.subject} {f.predicate}: {f.value}" for f in facts])

    # 5. Build system prompt with rolling summary & facts
    combo_extra = []
    if ctx.get("summary"):
        combo_extra.append(f"Conversation Summary:\n{ctx['summary']}")
    if extra_context:
        combo_extra.append(extra_context)

    system_prompt = build_system_prompt(
        extra_context="\n\n".join(combo_extra) if combo_extra else None,
        facts_summary=facts_summary
    )

    messages_payload: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for msg in ctx.get("recent_messages", []):
        messages_payload.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    tool_schemas = tool_registry.get_schemas()
    retry_count = 0
    final_text_accumulated = ""

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info(f"Stream agent loop iteration {iteration}/{MAX_ITERATIONS}")

        response = await llm.chat_completion(
            messages=messages_payload,
            tools=tool_schemas if tool_schemas else None,
            stream=False
        )

        choices = response.get("choices", [])
        if not choices:
            final_text_accumulated = "I apologize, but I received an empty response from the language model."
            yield f"data: {json.dumps({'type': 'token', 'content': final_text_accumulated})}\n\n"
            break

        msg_obj = choices[0].get("message", {})
        tool_calls, is_valid_json, parse_err = parse_tool_calls_from_response(msg_obj)

        if not is_valid_json and retry_count < 1:
            retry_count += 1
            messages_payload.append({
                "role": "assistant",
                "content": msg_obj.get("content") or ""
            })
            messages_payload.append({
                "role": "user",
                "content": f"[System Error] {parse_err}. Please format your tool call with valid JSON."
            })
            continue

        if not tool_calls:
            final_text_accumulated = msg_obj.get("content") or ""
            # Stream tokens to client
            # For smooth UX, yield words or chunks
            chunk_size = 8
            words = final_text_accumulated.split(" ")
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i+chunk_size])
                if i > 0:
                    chunk = " " + chunk
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                await asyncio.sleep(0.02)
            break

        # Save assistant message requesting tool calls
        assistant_msg_db = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=msg_obj.get("content") or f"[Tool call requested: {[t['name'] for t in tool_calls]}]",
            token_count=OllamaClient.estimate_tokens(msg_obj.get("content") or "")
        )
        db.add(assistant_msg_db)
        db.commit()
        db.refresh(assistant_msg_db)

        # Notify UI of tool calls starting
        for call in tool_calls:
            yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': call['name'], 'args': call['arguments']})}\n\n"

        assistant_payload_entry: Dict[str, Any] = {
            "role": "assistant",
            "content": msg_obj.get("content")
        }
        if "tool_calls" in msg_obj:
            assistant_payload_entry["tool_calls"] = msg_obj["tool_calls"]
        messages_payload.append(assistant_payload_entry)

        # Run tools in parallel
        tasks = [
            execute_single_tool(call, db=db, parent_message_id=assistant_msg_db.id)
            for call in tool_calls
        ]
        results = await asyncio.gather(*tasks)

        for call, tool_msg in results:
            messages_payload.append(tool_msg)
            # Notify UI of tool execution result
            try:
                res_obj = json.loads(tool_msg["content"])
            except Exception:
                res_obj = tool_msg["content"]
            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': call['name'], 'result': res_obj})}\n\n"
    else:
        final_text_accumulated = messages_payload[-1].get("content") or "Reached maximum iteration limit for tool calls."
        yield f"data: {json.dumps({'type': 'token', 'content': final_text_accumulated})}\n\n"

    # Save final assistant response to DB
    final_msg_db = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=final_text_accumulated,
        token_count=OllamaClient.estimate_tokens(final_text_accumulated)
    )
    db.add(final_msg_db)
    db.commit()

    yield f"data: {json.dumps({'type': 'done', 'conversation_id': conversation_id})}\n\n"

