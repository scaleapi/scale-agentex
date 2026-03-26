import json

from fastapi import APIRouter, HTTPException
from pydantic import Field

from src.config.environment_variables import EnvironmentVariables
from src.utils.logging import make_logger
from src.utils.model_utils import BaseModel

logger = make_logger(__name__)

router = APIRouter(
    prefix="/evals",
    tags=["Evals"],
)


class ConversationMessage(BaseModel):
    role: str = Field(..., title="Message role (user, assistant, tool)")
    content: str = Field(..., title="Message content")
    tool_calls: list[dict] | None = Field(None, title="Tool calls if any")
    name: str | None = Field(None, title="Tool name if role is tool")


class GenerateEvalRequest(BaseModel):
    messages: list[ConversationMessage] = Field(
        ..., title="The conversation messages to generate an eval from"
    )
    notes: str = Field(
        ..., title="User description of what went wrong or right"
    )
    agent_name: str = Field(..., title="Agent name")
    task_id: str = Field(..., title="Task ID")


class EvalCriteria(BaseModel):
    type: str = Field(..., title="Eval type: llm_judge or code_check")
    rubric: str = Field(..., title="Evaluation rubric")
    choices: list[str] = Field(..., title="Possible evaluation outcomes")


class GenerateEvalResponse(BaseModel):
    input: str = Field(..., title="Input to send to agent when re-running")
    expected_behavior: str = Field(
        ..., title="What the agent should do"
    )
    eval_criteria: EvalCriteria = Field(
        ..., title="Generated evaluation criteria"
    )
    tags: list[str] = Field(..., title="Tags for categorization")


SYSTEM_PROMPT = """You are an expert at creating evaluations for AI agents. Given a conversation between a user and an agent, plus the user's notes about what went wrong or right, generate a structured eval case.

You must return a JSON object with exactly these fields:
- "input": The user message or input that should be sent to the agent when re-running this eval. Extract the core user request from the conversation.
- "expected_behavior": A clear description of what the agent should do correctly. Be specific about tools to call, format of response, and correctness criteria.
- "eval_criteria": An object with:
  - "type": Always "llm_judge" for now
  - "rubric": A numbered list of specific things to check. Each item should be a yes/no question. Be specific and reference the actual expected behavior.
  - "choices": ["pass", "partial", "fail"]
- "tags": An array of relevant tags. Include things like "tool_use" if tools are involved, "multi_turn" if conversation has multiple turns, "regression" if something went wrong, "golden" if this is a positive example.

Focus the rubric on what the user described in their notes. Make it specific enough that an LLM judge can reliably evaluate it."""


@router.post(
    "/generate",
    response_model=GenerateEvalResponse,
)
async def generate_eval_criteria(
    request: GenerateEvalRequest,
) -> GenerateEvalResponse:
    """Generate eval criteria from a conversation using an LLM."""
    import litellm

    env = EnvironmentVariables.from_env()

    if not env.OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY not configured. Set it in your environment to enable eval generation.",
        )

    # Build the conversation context for the LLM
    conversation_text = ""
    for msg in request.messages:
        role_label = msg.role.upper()
        conversation_text += f"[{role_label}]: {msg.content}\n"
        if msg.tool_calls:
            for tc in msg.tool_calls:
                conversation_text += f"  -> Tool call: {tc.get('name', 'unknown')}({json.dumps(tc.get('arguments', {}))})\n"

    user_prompt = f"""Here is a conversation between a user and the agent "{request.agent_name}":

{conversation_text}

The user's notes about this interaction:
"{request.notes}"

Generate a structured eval case for this interaction. Return only valid JSON."""

    try:
        response = await litellm.acompletion(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            api_key=env.OPENAI_API_KEY,
        )

        result_text = response.choices[0].message.content
        result = json.loads(result_text)

        return GenerateEvalResponse(
            input=result.get("input", ""),
            expected_behavior=result.get("expected_behavior", ""),
            eval_criteria=EvalCriteria(
                type=result.get("eval_criteria", {}).get("type", "llm_judge"),
                rubric=result.get("eval_criteria", {}).get("rubric", ""),
                choices=result.get("eval_criteria", {}).get(
                    "choices", ["pass", "partial", "fail"]
                ),
            ),
            tags=result.get("tags", []),
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        raise HTTPException(
            status_code=500,
            detail="LLM returned invalid JSON. Please try again.",
        )
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate eval criteria: {str(e)}",
        )
