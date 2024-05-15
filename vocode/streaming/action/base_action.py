import asyncio
from typing import Any, Dict, Generic, Optional, Type, TypeVar, TYPE_CHECKING
from vocode.streaming.action.utils import exclude_keys_recursive
from vocode.streaming.models.actions import (
    ActionConfig,
    ActionInput,
    ActionOutput,
    ActionType,
    ParametersType,
    ResponseType,
)

if TYPE_CHECKING:
    from vocode.streaming.utils.state_manager import ConversationStateManager

ActionConfigType = TypeVar("ActionConfigType", bound=ActionConfig)


class BaseAction(Generic[ActionConfigType, ParametersType, ResponseType]):
    description: str = ""

    def __init__(
        self,
        action_config: ActionConfigType,
        should_respond: bool = False,
        quiet: bool = False,
        is_interruptible: bool = True,
    ):
        self.action_config = action_config
        self.should_respond = should_respond
        self.quiet = quiet
        self.is_interruptible = is_interruptible

    def attach_conversation_state_manager(
        self, conversation_state_manager: "ConversationStateManager"
    ):
        self.conversation_state_manager = conversation_state_manager

    async def run(
        self, action_input: ActionInput[ParametersType]
    ) -> ActionOutput[ResponseType]:
        raise NotImplementedError

    @property
    def parameters_type(self) -> Type[ParametersType]:
        raise NotImplementedError

    @property
    def response_type(self) -> Type[ResponseType]:
        raise NotImplementedError

    def get_openai_function(self):
        if hasattr(self.parameters_type, "schema_from_config"):
            parameters_schema = self.parameters_type.schema_from_config(self.action_config)
        else:
            parameters_schema = self.parameters_type.schema()
        parameters_schema = exclude_keys_recursive(parameters_schema, {"title"})
        if self.should_respond:
            parameters_schema["properties"][
                "user_message"
            ] = self._user_message_param_info()
            required = parameters_schema.get("required", [])
            required.append("user_message")
            parameters_schema["required"] = required

        return {
            "name": self.action_config.type,
            "description": self.description,
            "parameters": parameters_schema,
        }

    def create_action_input(
        self,
        conversation_id: str,
        params: Dict[str, Any],
        user_message_tracker: Optional[asyncio.Event] = None,
    ) -> ActionInput[ParametersType]:
        if "user_message" in params:
            del params["user_message"]
        return ActionInput(
            action_config=self.action_config,
            conversation_id=conversation_id,
            params=self.parameters_type(**params),
            user_message_tracker=user_message_tracker,
        )

    def _user_message_param_info(self):
        return {
            "type": "string",
            "description": """Explanation for the user that you use this tool. Use the language being used in this conversation. For example, "Let me check the weather in San Francisco CA for you.""",
        }
