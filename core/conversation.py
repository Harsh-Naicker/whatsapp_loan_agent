# core/conversation.py

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import openai
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('core.conversation')

class ConversationEngine:
    """Core conversation engine for the WhatsApp Loan-Against-Property Agent"""
    
    # Conversation states
    class State:
        INITIAL = "initial"
        INTRODUCTION = "introduction"
        QUALIFYING = "qualifying"
        PROPERTY_DETAILS = "property_details"
        LOAN_DETAILS = "loan_details"
        OBJECTION_HANDLING = "objection_handling"
        CLOSING = "closing"
        FOLLOW_UP_SCHEDULING = "follow_up_scheduling"
        COMPLETED = "completed"
        NOT_INTERESTED = "not_interested"
    
    # Customer intents
    class Intent:
        INTERESTED = "interested"
        NEEDS_MORE_INFO = "needs_more_info"
        OBJECTION = "objection"
        NOT_INTERESTED = "not_interested"
        ASKING_QUESTION = "asking_question"
        FOLLOW_UP_LATER = "follow_up_later"
    
    def __init__(self, language="english"):
        """
        Initialize the conversation engine
        
        Args:
            language: Language to use for conversation
        """
        self.language = language
        self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.DEFAULT_AI_MODEL
        self.max_conversation_tokens = 4000  # Limit history size
        self.load_prompts()
        
        # Setup state transition map
        self.state_transitions = {
            self.State.INITIAL: {
                self.Intent.INTERESTED: self.State.INTRODUCTION,
                self.Intent.NEEDS_MORE_INFO: self.State.INTRODUCTION,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                self.Intent.ASKING_QUESTION: self.State.INTRODUCTION,
            },
            self.State.INTRODUCTION: {
                self.Intent.INTERESTED: self.State.QUALIFYING,
                self.Intent.NEEDS_MORE_INFO: self.State.QUALIFYING,
                self.Intent.OBJECTION: self.State.OBJECTION_HANDLING,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                self.Intent.ASKING_QUESTION: self.State.QUALIFYING,
            },
            self.State.QUALIFYING: {
                self.Intent.INTERESTED: self.State.PROPERTY_DETAILS,
                self.Intent.NEEDS_MORE_INFO: self.State.QUALIFYING,
                self.Intent.OBJECTION: self.State.OBJECTION_HANDLING,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                self.Intent.ASKING_QUESTION: self.State.QUALIFYING,
                self.Intent.FOLLOW_UP_LATER: self.State.FOLLOW_UP_SCHEDULING,
            },
            self.State.PROPERTY_DETAILS: {
                self.Intent.INTERESTED: self.State.LOAN_DETAILS,
                self.Intent.NEEDS_MORE_INFO: self.State.PROPERTY_DETAILS,
                self.Intent.OBJECTION: self.State.OBJECTION_HANDLING,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                self.Intent.ASKING_QUESTION: self.State.PROPERTY_DETAILS,
                self.Intent.FOLLOW_UP_LATER: self.State.FOLLOW_UP_SCHEDULING,
            },
            self.State.LOAN_DETAILS: {
                self.Intent.INTERESTED: self.State.CLOSING,
                self.Intent.NEEDS_MORE_INFO: self.State.LOAN_DETAILS,
                self.Intent.OBJECTION: self.State.OBJECTION_HANDLING,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                self.Intent.ASKING_QUESTION: self.State.LOAN_DETAILS,
                self.Intent.FOLLOW_UP_LATER: self.State.FOLLOW_UP_SCHEDULING,
            },
            self.State.OBJECTION_HANDLING: {
                self.Intent.INTERESTED: self.State.LOAN_DETAILS,
                self.Intent.NEEDS_MORE_INFO: self.State.LOAN_DETAILS,
                self.Intent.OBJECTION: self.State.OBJECTION_HANDLING,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                self.Intent.ASKING_QUESTION: self.State.LOAN_DETAILS,
                self.Intent.FOLLOW_UP_LATER: self.State.FOLLOW_UP_SCHEDULING,
            },
            self.State.CLOSING: {
                self.Intent.INTERESTED: self.State.COMPLETED,
                self.Intent.NEEDS_MORE_INFO: self.State.LOAN_DETAILS,
                self.Intent.OBJECTION: self.State.OBJECTION_HANDLING,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                self.Intent.ASKING_QUESTION: self.State.LOAN_DETAILS,
                self.Intent.FOLLOW_UP_LATER: self.State.FOLLOW_UP_SCHEDULING,
            },
            self.State.FOLLOW_UP_SCHEDULING: {
                self.Intent.INTERESTED: self.State.LOAN_DETAILS,
                self.Intent.NEEDS_MORE_INFO: self.State.LOAN_DETAILS,
                self.Intent.NOT_INTERESTED: self.State.NOT_INTERESTED,
                # Default is to stay in follow-up scheduling
            },
            # Terminal states
            self.State.COMPLETED: {},
            self.State.NOT_INTERESTED: {
                self.Intent.INTERESTED: self.State.INTRODUCTION,  # If they change their mind
            },
        }
    
    def load_prompts(self):
        """Load conversation prompts for the current language"""
        prompt_dir = Path(settings.BASE_DIR) / 'prompts' / self.language
        
        # Create prompt directory if it doesn't exist
        if not prompt_dir.exists():
            prompt_dir.mkdir(parents=True)
            
            # Create a default prompts file
            default_prompts = {
                "intent_detection": "You are an assistant analyzing a customer conversation about loan-against-property. Based on the conversation history and the customer's latest message, determine their primary intent from these categories: interested, needs_more_info, objection, not_interested, asking_question, follow_up_later.\n\nConversation history:\n{history}\n\nCustomer's message: {message}\n\nIdentify the customer's intent as exactly one of: interested, needs_more_info, objection, not_interested, asking_question, follow_up_later. Respond with only that category name.",
                
                "information_extraction": "Extract key information from the customer message about their property and loan requirements. Return the information as a JSON object with any of these fields if present: property_type, property_location, property_value, loan_amount_needed, loan_purpose, current_loans, monthly_income, ownership_status, urgency, concerns.\n\nCustomer message: {message}\n\nCurrent known information: {current_profile}\n\nReturn only a JSON object with the newly extracted information. Do not include already known information unless the customer has changed or corrected it.",
                
                "initial": "You are a professional loan advisor for a reputable financial institution. You're reaching out to introduce loan-against-property options. Be friendly but professional. Briefly introduce yourself and mention that your company offers competitive loan-against-property services. Ask if they own property and if they've considered using it to secure financing. Keep your response concise, under 3 sentences.\n\nCustomer profile: {profile}\n\nRespond in a conversational, professional tone.",
                
                "introduction": "You are a loan-against-property advisor. The customer has shown initial interest. Provide a brief overview of loan-against-property benefits (quick processing, competitive interest rates, flexible tenure). Then ask about their property type and location to better understand their situation. Be concise but engaging.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond in a way that builds trust and encourages the customer to share more details.",
                
                "qualifying": "You are a loan advisor qualifying a potential customer. Based on the conversation, assess if they meet basic eligibility: property ownership, property valuation sufficient for loan amount, income stability for repayment.\n\nIf missing key information, ask focused questions about: property type/location/value, loan amount needed, current income, and loan purpose. Don't ask for personal identification information. Keep your response under 4 sentences and focus on the most important missing information first.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond professionally and show understanding of their needs.",
                
                "property_details": "You are a loan-against-property specialist. The customer has shared some property information. Acknowledge what they've shared and explain how their property type/location affects loan eligibility. If they haven't mentioned property value, ask for an approximate market value, as this determines maximum loan amount (typically 60-70% of property value).\n\nBe informative but concise. Avoid jargon. If they've mentioned loan purpose, acknowledge how this purpose aligns with loan-against-property benefits.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond in an informative, trustworthy manner.",
                
                "loan_details": "You are a loan-against-property advisor discussing specific loan details. Based on their property value (if known), mention they could qualify for approximately 60-70% of property value. If they've specified a loan amount, confirm if this seems feasible based on their property.\n\nDiscuss one or two key benefits: competitive interest rates (starting at 8.5%), flexible tenure (up to 15 years), or minimal documentation requirements. Then ask about their preferred loan tenure or monthly budget for EMI payments to further personalize recommendations.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond clearly and build confidence in your expertise.",
                
                "objection_handling": "You are a loan advisor addressing customer concerns about loan-against-property. Identify their specific objection (interest rates, processing time, documentation, property valuation, etc.).\n\nAcknowledge their concern respectfully. Provide a brief, factual response that addresses their specific objection. Avoid being defensive. Where appropriate, mention how your company's offering might address their concern better than alternatives.\n\nEnd with an open question to understand if you've addressed their concern or if they have other questions.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond empathetically while maintaining professionalism.",
                
                "closing": "You are a loan advisor moving toward application. The customer shows serious interest. Summarize the key points discussed (property details, approximate loan amount, purpose).\n\nExplain the next steps: 1) Complete application form, 2) Submit property documents, 3) Property valuation, 4) Loan approval and disbursement. Mention the process typically takes 7-10 business days.\n\nAsk if they'd like to proceed with an application or if they need more information before deciding. Offer to connect them with a loan officer who can process their application.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond concisely and with a sense of positive momentum.",
                
                "follow_up_scheduling": "You are a loan advisor concluding a conversation with a potential customer who isn't ready to proceed immediately. Acknowledge their position without pressure. Summarize the key points discussed about loan-against-property.\n\nAsk when would be a good time to follow up (suggest a specific timeframe like next week or next month based on their indicated level of interest).\n\nThank them for their time and mention you'll send a quick summary of discussed loan options to their number for future reference.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond respectfully and leave the door open for future communication.",
                
                "not_interested": "You are a loan advisor responding to a customer who has indicated they're not interested in a loan-against-property. Respect their decision without pushing. Thank them for their time. Briefly mention that circumstances and needs can change, and they're welcome to reach out in the future if they reconsider.\n\nDo not try to change their mind or ask why they're not interested. Keep the message under 3 sentences.\n\nConversation history: {history}\nCustomer profile: {profile}\n\nRespond respectfully and concisely."
            }
            
            # Save default prompts
            with open(prompt_dir / 'prompts.json', 'w') as f:
                json.dump(default_prompts, f, indent=4)
        
        # Load prompts from file
        try:
            with open(prompt_dir / 'prompts.json', 'r') as f:
                self.prompts = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load prompts: {str(e)}")
            # Fall back to empty dict, which will cause default prompts to be used
            self.prompts = {}
    
    def detect_intent(self, message: str, conversation_history: List[Dict[str, Any]]) -> Tuple[str, float]:
        """
        Detect customer intent from message
        
        Args:
            message: Customer's message
            conversation_history: List of previous exchanges
            
        Returns:
            Tuple of (intent, confidence_score)
        """
        # Format conversation history
        history_text = self._format_conversation_history(conversation_history)
        
        # Use intent detection prompt
        prompt = self.prompts.get("intent_detection", "Determine the intent of this message: {message}")
        prompt = prompt.replace("{history}", history_text).replace("{message}", message)
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You analyze customer intent in conversations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent results
                max_tokens=50  # Intent detection should be short
            )
            
            intent = response.choices[0].message.content.strip().lower()
            
            # Normalize intent to match our intent classes
            if intent in [self.Intent.INTERESTED, self.Intent.NEEDS_MORE_INFO, 
                         self.Intent.OBJECTION, self.Intent.NOT_INTERESTED,
                         self.Intent.ASKING_QUESTION, self.Intent.FOLLOW_UP_LATER]:
                normalized_intent = intent
            elif "interest" in intent:
                normalized_intent = self.Intent.INTERESTED
            elif "more info" in intent or "information" in intent:
                normalized_intent = self.Intent.NEEDS_MORE_INFO
            elif "object" in intent or "concern" in intent:
                normalized_intent = self.Intent.OBJECTION
            elif "not" in intent and ("interest" in intent or "want" in intent):
                normalized_intent = self.Intent.NOT_INTERESTED
            elif "question" in intent or "ask" in intent:
                normalized_intent = self.Intent.ASKING_QUESTION
            elif "follow" in intent or "later" in intent:
                normalized_intent = self.Intent.FOLLOW_UP_LATER
            else:
                # Default to needing more info if we can't classify
                normalized_intent = self.Intent.NEEDS_MORE_INFO
            
            # Calculate confidence based on model's completion (simple approach)
            confidence = 0.7  # Base confidence
            if response.choices[0].finish_reason == "stop":
                confidence += 0.1
            
            logger.info(f"Detected intent: {normalized_intent} with confidence: {confidence}")
            return normalized_intent, confidence
            
        except Exception as e:
            logger.error(f"Error detecting intent: {str(e)}")
            # Return default intent with low confidence
            return self.Intent.NEEDS_MORE_INFO, 0.5
    
    def extract_information(self, message: str, current_profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract key information from customer message
        
        Args:
            message: Customer's message
            current_profile: Current customer profile information
            
        Returns:
            Dictionary with extracted information
        """
        # Use information extraction prompt
        prompt = self.prompts.get("information_extraction", "Extract information from this message: {message}")
        prompt = prompt.replace("{message}", message).replace("{current_profile}", json.dumps(current_profile))
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You extract structured information from messages and respond in JSON format."},
                    {"role": "user", "content": f"Provide a JSON response: {prompt}"}
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            
            extracted_info_text = response.choices[0].message.content.strip()
            
            try:
                extracted_info = json.loads(extracted_info_text)
                
                # Clean up extracted info
                cleaned_info = {}
                for key, value in extracted_info.items():
                    # Skip null or empty values
                    if value is None or value == "" or value == []:
                        continue
                    
                    # Normalize property values and loan amounts (convert text to numbers)
                    if key == "property_value" or key == "loan_amount_needed":
                        if isinstance(value, str):
                            # Extract numeric portion from strings like "80 lakhs" or "1.5 crores"
                            value = self._convert_indian_currency_to_number(value)
                    
                    cleaned_info[key] = value
                
                return cleaned_info
            except json.JSONDecodeError:
                logger.error(f"Failed to parse extracted info: {extracted_info_text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error extracting information: {str(e)}")
            return {}
    
    def generate_response(self, message: str, customer_profile: Dict[str, Any], conversation_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate appropriate response based on conversation state and customer intent
        
        Args:
            message: Customer's message
            customer_profile: Customer profile information
            conversation_history: List of previous exchanges
            
        Returns:
            Dictionary with response details
        """
        # Extract current state
        current_state = customer_profile.get("conversation_state", self.State.INITIAL)
        
        # Detect intent
        intent, confidence = self.detect_intent(message, conversation_history)
        
        # Extract information from message
        extracted_info = self.extract_information(message, customer_profile)
        
        # Update state based on intent and current state
        new_state = self._update_state(current_state, intent)
        
        # Get prompt for the new state
        prompt_key = new_state if new_state in self.prompts else "initial"
        if prompt_key not in self.prompts:
            # Fallback to a generic prompt
            prompt = "You are a loan advisor. Respond professionally to the customer: {message}"
        else:
            prompt = self.prompts[prompt_key]
        
        # Format conversation history for prompt
        history_text = self._format_conversation_history(conversation_history)
        
        # Format prompt with variables
        prompt = prompt.replace("{history}", history_text)
        prompt = prompt.replace("{profile}", json.dumps(customer_profile))
        prompt = prompt.replace("{message}", message)
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful loan-against-property advisor."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Determine follow-up timing
            follow_up_date = self._calculate_follow_up_date(intent, new_state)
            
            # Determine if audio response would be beneficial
            should_generate_audio = self._should_generate_audio(response_text, new_state)
            
            return {
                "text": response_text,
                "state": new_state,
                "previous_state": current_state,
                "intent": intent,
                "confidence": confidence,
                "extracted_info": extracted_info,
                "should_generate_audio": should_generate_audio,
                "follow_up_date": follow_up_date,
                "analysis": {
                    "message_length": len(message),
                    "response_length": len(response_text),
                    "state_changed": new_state != current_state
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            # Return a fallback response
            return {
                "text": "I apologize, but I'm having trouble processing your request at the moment. Could you please try again or contact our customer service for assistance?",
                "state": current_state,  # Keep the same state
                "previous_state": current_state,
                "intent": intent,
                "confidence": 0.5,
                "extracted_info": {},
                "should_generate_audio": False,
                "follow_up_date": None,
                "analysis": {
                    "error": str(e),
                    "fallback": True
                }
            }
    
    def generate_followup(self, followup_context: Dict[str, Any], language: str = None) -> Dict[str, Any]:
        """
        Generate a follow-up message
        
        Args:
            followup_context: Context for the follow-up
            language: Language to use (defaults to instance language)
            
        Returns:
            Dictionary with follow-up message details
        """
        # Use specified language or default to instance language
        lang = language or self.language
        
        # Create a system prompt for follow-up
        system_prompt = f"""You are a loan-against-property advisor following up with a customer.
You previously spoke with them about a loan against their property.
Your goal is to check if they're ready to proceed or if they need more information.
Be polite, professional, and not pushy. Reference specific details from your previous conversation."""
        
        user_prompt = f"""Generate a follow-up message for a customer with the following information:
        
Customer name: {followup_context.get('customer_name', 'there')}
Last conversation state: {followup_context.get('last_state', 'initial')}
Follow-up reason: {followup_context.get('follow_up_reason', 'general follow-up')}
Days since last contact: {followup_context.get('days_since_contact', 0)}
Property details: {json.dumps(followup_context.get('property_details', {}))}
Loan requirements: {json.dumps(followup_context.get('loan_requirements', {}))}

The message should be concise, personalized, and provide clear next steps.
"""
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Determine if audio would be beneficial
            should_generate_audio = len(response_text) > 200 or "urgent" in followup_context.get('follow_up_reason', '').lower()
            
            # Determine next state based on previous state
            last_state = followup_context.get('last_state', self.State.INITIAL)
            if last_state == self.State.NOT_INTERESTED:
                new_state = self.State.NOT_INTERESTED
            elif last_state == self.State.COMPLETED:
                new_state = self.State.COMPLETED
            else:
                new_state = self.State.FOLLOW_UP_SCHEDULING
            
            return {
                "text": response_text,
                "should_generate_audio": should_generate_audio,
                "new_state": new_state
            }
            
        except Exception as e:
            logger.error(f"Error generating follow-up: {str(e)}")
            # Return a fallback follow-up
            return {
                "text": f"Hello {followup_context.get('customer_name', 'there')}, this is ABC Finance following up on our conversation about a loan against your property. We're still here to help if you have any questions or would like to proceed. Feel free to reach out at your convenience.",
                "should_generate_audio": False,
                "new_state": followup_context.get('last_state', self.State.INITIAL)
            }
    
    def generate_campaign_message(self, template: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a personalized campaign message
        
        Args:
            template: Message template
            customer_data: Customer data for personalization
            
        Returns:
            Dictionary with campaign message details
        """
        # Replace template variables with customer data
        personalized_message = template
        
        for key, value in customer_data.items():
            if isinstance(value, str):
                placeholder = f"{{{key}}}"
                personalized_message = personalized_message.replace(placeholder, value)
        
        # Extract template name and parameters based on the first line
        # Format: Template Name: {template_name}
        template_name = "general_outreach"  # Default
        template_params = {}
        
        lines = template.strip().split('\n')
        if lines and ":" in lines[0]:
            header_parts = lines[0].split(':', 1)
            if header_parts[0].strip().lower() == "template name":
                template_name = header_parts[1].strip()
                # Remove the first line from personalized message
                personalized_message = '\n'.join(lines[1:]).strip()
        
        # Extract template parameters
        for key, value in customer_data.items():
            if isinstance(value, str):
                template_params[key] = value
        
        # Add default parameters if needed
        if "name" not in template_params and "customer_name" in customer_data:
            template_params["name"] = customer_data["customer_name"]
            
        if "default_text" not in template_params:
            template_params["default_text"] = personalized_message[:120]  # Truncate if too long
        
        return {
            "preview": personalized_message,
            "template_name": template_name,
            "template_params": template_params
        }
        
    def generate_audio_message(self, text: str, language: str = None) -> str:
        """
        Generate audio for a text message using TTS
        
        Args:
            text: Message text
            language: Language to use
            
        Returns:
            Path to the generated audio file
        """
        # This is a placeholder - in a real implementation, you would use a TTS service
        # For now, we'll just return a placeholder path
        return f"/tmp/audio_{int(time.time())}.mp3"
    
    def _update_state(self, current_state: str, intent: str) -> str:
        """
        Update conversation state based on intent and current state
        
        Args:
            current_state: Current conversation state
            intent: Detected customer intent
            
        Returns:
            New conversation state
        """
        # Get transitions for current state
        transitions = self.state_transitions.get(current_state, {})
        
        # If there's a transition for this intent, use it
        if intent in transitions:
            return transitions[intent]
            
        # Otherwise, stay in the same state
        return current_state
    
    def _format_conversation_history(self, conversation_history: List[Dict[str, Any]]) -> str:
        """
        Format conversation history for inclusion in prompts
        
        Args:
            conversation_history: List of conversation exchanges
            
        Returns:
            Formatted conversation history text
        """
        formatted_history = []
        
        # Take the most recent exchanges that fit within token limit
        for exchange in conversation_history[-10:]:  # Limit to last 10 exchanges
            if exchange.get("direction") == "inbound":
                formatted_history.append(f"Customer: {exchange.get('content', '')}")
            else:
                formatted_history.append(f"Agent: {exchange.get('content', '')}")
        
        return "\n".join(formatted_history)
    
    def _should_generate_audio(self, response_text: str, state: str) -> bool:
        """
        Determine if audio response would be beneficial
        
        Args:
            response_text: Generated response text
            state: Conversation state
            
        Returns:
            True if audio should be generated, False otherwise
        """
        # Generate audio for longer responses
        if len(response_text) > 300:
            return True
            
        # Generate audio for emotionally significant states
        if state in [self.State.OBJECTION_HANDLING, self.State.CLOSING, self.State.NOT_INTERESTED]:
            return True
            
        # Generate audio for complex information
        if state in [self.State.LOAN_DETAILS] and any(term in response_text.lower() for term in 
                                                    ["interest rate", "emi", "tenure", "processing fee"]):
            return True
            
        return False
    
    def _calculate_follow_up_date(self, intent: str, state: str) -> Optional[str]:
        """
        Calculate when to follow up based on conversation
        
        Args:
            intent: Detected customer intent
            state: Conversation state
            
        Returns:
            Follow-up interval string (e.g., "30d") or None
        """
        if intent == self.Intent.FOLLOW_UP_LATER:
            return "7d"  # Follow up after 1 week
            
        if state == self.State.FOLLOW_UP_SCHEDULING:
            return "14d"  # Default follow-up after 2 weeks
            
        if state == self.State.NOT_INTERESTED:
            return "90d"  # Follow up after 90 days if not interested
            
        if state == self.State.OBJECTION_HANDLING:
            return "21d"  # Follow up after 3 weeks if there were objections
            
        if state == self.State.LOAN_DETAILS and intent != self.Intent.INTERESTED:
            return "30d"  # Follow up after 30 days if discussing loan details but not fully interested
            
        # No follow-up for other states
        return None
    
    def _convert_indian_currency_to_number(self, value_str: str) -> float:
        """
        Convert Indian currency expressions to numeric values
        
        Args:
            value_str: String representation of value (e.g., "80 lakhs", "1.5 crores")
            
        Returns:
            Numeric value in base units (rupees)
        """
        if not isinstance(value_str, str):
            return value_str
            
        value_str = value_str.lower().strip()
        
        # Try to extract numeric portion
        import re
        numeric_match = re.search(r'(\d+\.?\d*)', value_str)
        if not numeric_match:
            return 0
            
        numeric_value = float(numeric_match.group(1))
        
        # Check for multipliers
        if "lakh" in value_str or "lac" in value_str:
            return numeric_value * 100000
        elif "crore" in value_str or "cr" in value_str:
            return numeric_value * 10000000
        elif "k" in value_str or "thousand" in value_str:
            return numeric_value * 1000
        else:
            return numeric_value