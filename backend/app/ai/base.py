from abc import ABC, abstractmethod

from app.agents.models import AgentDecision

class LLMProvider(ABC):

    @abstractmethod
    def analyze_delayed_order(
        self,
        system_prompt: str,
        user_input:str,
    ) -> AgentDecision:
        pass