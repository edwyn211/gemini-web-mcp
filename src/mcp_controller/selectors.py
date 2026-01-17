import json
from pathlib import Path
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field, field_validator


class SelectorConfig(BaseModel):
    """
    Configuration for a single selector with primary, fallbacks, and validator.
    Supports both old format (string) and new format (dict with primary/fallbacks).
    """

    primary: str = Field(..., description="Primary selector to try first")
    fallbacks: List[str] = Field(
        default_factory=list, description="Fallback selectors to try if primary fails"
    )
    validator: str | None = Field(
        None, description="Selector to validate the action completed"
    )

    # Additional fields for specific selectors
    dropdown_icon: str | None = None
    reasoning_option: str | None = None

    @classmethod
    def from_value(cls, value: Union[str, Dict[str, Any]]) -> "SelectorConfig":
        """
        Create a SelectorConfig from either a string or dict.

        Args:
            value: Either a string selector or a dict with primary/fallbacks

        Returns:
            SelectorConfig instance
        """
        if isinstance(value, str):
            # Old format: just a string selector
            return cls(primary=value, fallbacks=[])
        elif isinstance(value, dict):
            # New format: dict with primary, fallbacks, etc.
            return cls(**value)
        else:
            raise ValueError(f"Invalid selector value type: {type(value)}")


class GeminiSelectors(BaseModel):
    """
    Pydantic model to load and validate Gemini UI selectors from a JSON file.
    Now supports enhanced selectors with primary, fallbacks, and validators.
    """

    new_chat_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the 'New chat' button."
    )
    prompt_textarea: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the main prompt input textarea."
    )
    send_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the button to send the prompt."
    )
    mic_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the microphone button (idle state)."
    )
    last_response: Union[str, SelectorConfig] = Field(
        ..., description="Selector to grab the last response from Gemini."
    )
    canvas_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the Canvas tool button."
    )
    deep_research_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the Deep Research tool button."
    )
    deep_research_confirm_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the Deep Research plan confirmation button."
    )
    deep_research_plan_ready: Union[str, SelectorConfig] = Field(
        ..., description="Selector to detect when the Deep Research plan is ready."
    )
    tools_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the tools button."
    )
    mode_selector: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the mode selector text."
    )
    stop_button: Union[str, SelectorConfig] = Field(
        ..., description="Selector for the stop/cancel button during generation."
    )
    show_more: Union[str, SelectorConfig] = Field(
        ...,
        description="Selector for the 'Show more' button to expand truncated responses.",
    )

    @field_validator("*", mode="before")
    @classmethod
    def convert_to_selector_config(cls, value):
        """Convert all selector fields to SelectorConfig objects"""
        if isinstance(value, (str, dict)):
            return SelectorConfig.from_value(value)
        return value

    def get_primary(self, field_name: str) -> str:
        """
        Get the primary selector for a field.

        Args:
            field_name: Name of the selector field

        Returns:
            Primary selector string
        """
        selector = getattr(self, field_name)
        if isinstance(selector, SelectorConfig):
            return selector.primary
        return selector

    def get_all_selectors(self, field_name: str) -> List[str]:
        """
        Get all selectors (primary + fallbacks) for a field.

        Args:
            field_name: Name of the selector field

        Returns:
            List of selectors in priority order
        """
        selector = getattr(self, field_name)
        if isinstance(selector, SelectorConfig):
            return [selector.primary] + selector.fallbacks
        return [selector]

    def get_validator(self, field_name: str) -> str | None:
        """
        Get the validator selector for a field.

        Args:
            field_name: Name of the selector field

        Returns:
            Validator selector string or None
        """
        selector = getattr(self, field_name)
        if isinstance(selector, SelectorConfig):
            return selector.validator
        return None

    def as_dict(self) -> Dict[str, Any]:
        """
        Convert selectors to a dictionary format suitable for StateValidator.

        Returns:
            Dictionary with selector configurations
        """
        result = {}
        for field_name in self.model_fields.keys():
            selector = getattr(self, field_name)
            if isinstance(selector, SelectorConfig):
                result[field_name] = selector.model_dump()
            else:
                result[field_name] = selector
        return result


def load_selectors(config_path: Path) -> GeminiSelectors:
    """
    Loads selectors from the specified JSON configuration file.
    """
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Selector configuration file not found at {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Remove comment field if present
    data.pop("_comment", None)

    return GeminiSelectors(**data)


# Define the default path to the selectors config relative to the project root
# This assumes the script is run from the project root.
CONFIG_PATH = Path("config/selectors.json")


class SelectorsManager:
    """
    Singleton to manage the current state of selectors.
    Allows dynamic updates at runtime (e.g. from Redis).
    """

    def __init__(self):
        self._selectors: GeminiSelectors = load_selectors(CONFIG_PATH)

    @property
    def current(self) -> GeminiSelectors:
        """Get the current active selectors."""
        return self._selectors

    def update(self, new_selectors: GeminiSelectors):
        """Update the active selectors."""
        self._selectors = new_selectors
        
    def update_from_dict(self, data: Dict[str, Any]):
        """Update from a dictionary configuration."""
        self._selectors = GeminiSelectors(**data)


# Global singleton instance
selector_manager = SelectorsManager()

# For backward compatibility (though using selector_manager.current is preferred)
# properties of this object won't update automatically if imported directly as 'from selectors import gemini_selectors'
# but 'gemini_selectors' variable here will stay pointing to the initial object.
# Consumers should be updated to use selector_manager.current
gemini_selectors = selector_manager.current
