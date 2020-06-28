import sys
import logging
        
from typing import Any, Text, Dict, List
#
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# dummy action when using voice interface to signal switch back to active listening
class ActionNavigateTo(Action):
#
    def name(self) -> Text:
        return "action_navigate_to"
#
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger = logging.getLogger(__name__)    
        logger.debug('ACTION_nav')
        dispatcher.utter_message(text="navigate")
        return []
        # [SlotSet("hermod_force_continue", "true"), SlotSet("hermod_force_end", None)] 