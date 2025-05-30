"""
End-to-end workflow definitions for the Mathematical Multimodal LLM System.

This module defines comprehensive workflows that utilize all system components
to process mathematical queries from start to finish.
"""
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import uuid
import time
import os
import asyncio

from ..agents.registry import AgentRegistry
from ..message_bus.message_formats import create_message
from core.agent.multimodal_integration import MultimodalLLMIntegration
from math_processing.agent.math_multimodal_integration import MathMultimodalIntegration
from multimodal.context.context_manager import ContextManager
from multimodal.unified_pipeline.input_processor import InputProcessor
from multimodal.unified_pipeline.content_router import ContentRouter
from visualization.agent.viz_agent import VisualizationAgent
from ..context.context_manager import get_context_manager
from orchestration.agents.chat_analysis_agent import get_chat_analysis_agent

logger = logging.getLogger(__name__)

class EndToEndWorkflowManager:
    """Manager for end-to-end workflows in the system."""
    
    def __init__(self, registry: AgentRegistry, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the end-to-end workflow manager.
        
        Args:
            registry: Agent registry
            config: Optional configuration dictionary
        """
        self.registry = registry
        self.config = config or {}
        
        try:
            # Get required services and agents
            self.context_manager = self._get_service("context_manager")
            self.input_processor = self._get_service("input_processor")
            self.content_router = self._get_service("content_router")
        
            # Try to get agent instances, but don't fail if they're not available
            try:
                self.core_llm_agent = self._get_agent("core_llm_agent")
                if self.core_llm_agent:
                    self.llm_integration = MultimodalLLMIntegration(self.core_llm_agent)
                    logger.info("Successfully initialized LLM integration")
                else:
                    logger.warning("Core LLM Agent not available - workflows will have limited functionality")
                    self.llm_integration = None
            except Exception as e:
                logger.warning(f"Failed to initialize Core LLM Agent: {str(e)}")
                self.core_llm_agent = None
                self.llm_integration = None
            
            try:
                self.math_agent = self._get_agent("math_computation_agent")
                if self.math_agent:
                    self.math_integration = MathMultimodalIntegration(self.math_agent)
                    logger.info("Successfully initialized Math integration")
                else:
                    logger.warning("Math Computation Agent not available - workflows will have limited functionality")
                    self.math_integration = None
            except Exception as e:
                logger.warning(f"Failed to initialize Math Computation Agent: {str(e)}")
                self.math_agent = None
                self.math_integration = None
        
            # Workflow storage
            self.active_workflows = {}
        
            logger.info("Initialized end-to-end workflow manager")
        except Exception as e:
            logger.error(f"Error initializing end-to-end workflow manager: {str(e)}")
            raise ValueError(f"Failed to initialize workflow manager: {str(e)}")
    
    def _get_service(self, service_id: str) -> Any:
        """
        Get a service instance from the registry.
        
        Args:
            service_id: Service identifier
            
        Returns:
            Service instance
        """
        service_info = self.registry.get_service_info(service_id)
        if not service_info or "instance" not in service_info:
            raise ValueError(f"Service not found or not initialized: {service_id}")
        return service_info["instance"]
    
    def _get_agent(self, agent_id: str) -> Any:
        """
        Get an agent instance from the registry.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Agent instance or None if not available
        """
        try:
            logger.info(f"Attempting to get agent instance: {agent_id}")
            agent_info = self.registry.get_agent_info(agent_id)
            
            if not agent_info:
                logger.error(f"Agent not found in registry: {agent_id}")
                return None

            if "instance" not in agent_info or agent_info["instance"] is None:
                logger.warning(f"Agent instance not initialized in registry: {agent_id}")
                # Check if instance exists directly in registry.agents
                raw_agent = self.registry.agents.get(agent_id, {})
                if "instance" in raw_agent and raw_agent["instance"] is not None:
                    logger.info(f"Found agent instance directly in registry.agents: {agent_id}")
                    return raw_agent["instance"]
                logger.error(f"No agent instance available for: {agent_id}")
                return None
                
            logger.info(f"Successfully retrieved agent instance: {agent_id}")
            return agent_info["instance"]
        except Exception as e:
            logger.error(f"Error getting agent {agent_id}: {str(e)}")
            return None
    
    def start_workflow(self, input_data: Dict[str, Any], 
                      context_id: Optional[str] = None,
                      conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Start a new end-to-end workflow.
        
        Args:
            input_data: Input data for the workflow
            context_id: Optional context ID
            conversation_id: Optional conversation ID
            
        Returns:
            Dictionary containing workflow information
        """
        # Generate workflow ID
        workflow_id = str(uuid.uuid4())
        
        # Create context if needed
        if not context_id:
            context = self.context_manager.create_context(conversation_id)
            context_id = context.context_id
        
        # Create workflow state
        workflow = {
            "id": workflow_id,
            "type": "end_to_end",
            "state": "initializing",
            "input_data": input_data,
            "context_id": context_id,
            "conversation_id": conversation_id,
            "steps": [],
            "current_step": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Store in active workflows
        self.active_workflows[workflow_id] = workflow
        
        # Start asynchronous processing
        self._process_workflow_async(workflow_id)
        
        return {
            "workflow_id": workflow_id,
            "context_id": context_id,
            "conversation_id": conversation_id,
            "state": "initializing",
            "message": "Workflow started successfully"
        }
    
    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get the current status of a workflow.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Dictionary containing workflow status
        """
        if workflow_id not in self.active_workflows:
            return {
                "success": False,
                "error": f"Workflow not found: {workflow_id}"
            }
        
        workflow = self.active_workflows[workflow_id]
        
        return {
            "workflow_id": workflow_id,
            "state": workflow["state"],
            "current_step": workflow["current_step"],
            "steps_completed": len(workflow["steps"]),
            "created_at": workflow["created_at"],
            "updated_at": workflow["updated_at"]
        }
    
    def get_workflow_result(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get the result of a completed workflow.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Dictionary containing workflow result
        """
        if workflow_id not in self.active_workflows:
            return {
                "success": False,
                "error": f"Workflow not found: {workflow_id}"
            }
        
        workflow = self.active_workflows[workflow_id]
        
        if workflow["state"] != "completed":
            return {
                "success": False,
                "error": f"Workflow not completed: {workflow_id}",
                "state": workflow["state"]
            }
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "result": workflow.get("result", {}),
            "steps": workflow["steps"]
        }
    
    def _process_workflow_async(self, workflow_id: str) -> None:
        """
        Process a workflow asynchronously.
        
        In a production system, this would be a background task.
        
        Args:
            workflow_id: Workflow identifier
        """
        # In a real implementation, this would be handled by a task queue or threads
        # For this example, we'll use asyncio to process it
        try:
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an event loop, so create a task instead of running a new event loop
                asyncio.create_task(self._process_workflow_async_impl(workflow_id))
            except RuntimeError:
                # No running event loop, safe to use asyncio.run()
                asyncio.run(self._process_workflow_async_impl(workflow_id))
        except Exception as e:
            logger.error(f"Error in async workflow processing: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Update workflow state
            workflow = self.active_workflows.get(workflow_id)
            if workflow:
                workflow["state"] = "error"
                workflow["error"] = str(e)
                workflow["updated_at"] = datetime.now().isoformat()
    
    async def _process_workflow_async_impl(self, workflow_id: str) -> None:
        """
        Actual implementation of asynchronous workflow processing.
        
        Args:
            workflow_id: Workflow identifier
        """
        try:
            workflow = self.active_workflows[workflow_id]
            workflow["state"] = "processing"
            workflow["steps"] = []
            
            # Step 1: Process the input
            self._update_workflow_step(workflow_id, "input_processing", "Processing input")
            input_data = workflow["input_data"]
            
            # Determine input type and process accordingly
            if "input_type" in input_data:
                # Already processed
                processed_input = input_data
            elif "content" in input_data:
                # Raw content
                content = input_data["content"]
                content_type = input_data.get("content_type", "text/plain")
                processed_input = self.input_processor.process_input(content, content_type)
            else:
                raise ValueError("Invalid input data format")
            
            # Add processed input to workflow
            workflow["processed_input"] = processed_input
            
            # Step 2: Check for ambiguities
            self._update_workflow_step(workflow_id, "ambiguity_checking", "Checking for ambiguities")
            
            # In a real implementation, this would check for ambiguities
            # For this example, we'll assume no ambiguities
            
            # Step 3: Route content to appropriate agents
            self._update_workflow_step(workflow_id, "content_routing", "Routing content to appropriate agents")
            
            routing_result = self.content_router.route_content(processed_input)
            workflow["routing_result"] = routing_result
            
            # Step 4: Process with appropriate agents
            self._update_workflow_step(workflow_id, "agent_processing", "Processing with specialized agents")
            
            # Handle different agent types
            agent_type = routing_result.get("agent_type", "core_llm")
            agent_result = None
            
            if agent_type == "ocr" or agent_type == "advanced_ocr":
                # Already processed by the input pipeline
                agent_result = routing_result.get("result", {})
                
            elif agent_type == "core_llm":
                # Check if LLM integration is available
                if hasattr(self, 'llm_integration') and self.llm_integration:
                    # Initial processing with LLM
                    try:
                        agent_result = self.llm_integration.process_multimodal_input(
                            processed_input,
                            {"conversation_id": workflow.get("conversation_id")}
                        )
                    except AttributeError as e:
                        logger.error(f"Error in LLM processing: {str(e)}")
                        # Create a placeholder result
                        agent_result = {
                            "success": False,
                            "error": f"LLM processing failed: {str(e)}",
                            "input_type": processed_input.get("input_type", "unknown"),
                            "response": "I'm sorry, I couldn't process your request due to a technical issue.",
                            "contains_math": False,
                            "original_input": processed_input
                        }
                else:
                    # Try to initialize the core_llm_agent now if it wasn't available during initialization
                    try:
                        if not hasattr(self, 'core_llm_agent') or not self.core_llm_agent:
                            self.core_llm_agent = self._get_agent("core_llm_agent")
                            if self.core_llm_agent:
                                self.llm_integration = MultimodalLLMIntegration(self.core_llm_agent)
                                logger.info("Successfully initialized LLM integration on-demand")
                                # Now process with the newly initialized LLM integration
                                agent_result = self.llm_integration.process_multimodal_input(
                                    processed_input,
                                    {"conversation_id": workflow.get("conversation_id")}
                                )
                            else:
                                logger.error("LLM agent is not available")
                                # Create a placeholder result
                                agent_result = {
                                    "success": False,
                                    "error": "LLM agent is not available",
                                    "input_type": processed_input.get("input_type", "unknown"),
                                    "response": "I'm sorry, I couldn't process your request due to a technical issue.",
                                    "contains_math": False,
                                    "original_input": processed_input
                                }
                    except Exception as e:
                        logger.error(f"Error initializing LLM agent: {str(e)}")
                        # Create a placeholder result
                        agent_result = {
                            "success": False,
                            "error": f"Error initializing LLM agent: {str(e)}",
                            "input_type": processed_input.get("input_type", "unknown"),
                            "response": "I'm sorry, I couldn't process your request due to a technical issue.",
                            "contains_math": False,
                            "original_input": processed_input
                        }
            
            # Step 4.5: Check if this is a visualization request and process accordingly
            self._update_workflow_step(workflow_id, "visualization_check", "Checking if visualization is needed")
            
            visualization_result = None
            
            # Try to initialize chat analysis agent if available
            chat_analysis_agent = None
            try:
                chat_analysis_agent = get_chat_analysis_agent()
            except Exception as e:
                logger.warning(f"Could not initialize chat analysis agent: {str(e)}")
            
            # If chat analysis agent is available, check if this is a visualization request
            if chat_analysis_agent:
                try:
                    # Extract the text content
                    text_content = ""
                    if processed_input.get("input_type") == "text":
                        text_content = processed_input.get("content", "")
                    
                    if text_content:
                        # Analyze the text for visualization requests
                        analysis_result = chat_analysis_agent.analyze_plot_request(text_content)
                        
                        # If this is a visualization request, process it
                        if analysis_result.get("success", False) and analysis_result.get("is_visualization_request", True):
                            logger.info(f"Detected visualization request: {analysis_result.get('plot_type')}")
                            
                            # Process visualization
                            visualization_result = await chat_analysis_agent.process_visualization_request(analysis_result)
                            workflow["visualization_result"] = visualization_result
                            
                            # If successful, update the agent_result to include visualization information
                            if visualization_result.get("success", False) and "file_path" in visualization_result:
                                # If we have a successful agent result, update it
                                if "success" in agent_result and agent_result.get("success", False):
                                    if "response" in agent_result:
                                        # Append visualization info to the response
                                        viz_info = f"\n\nI've created a visualization based on your request. "
                                        viz_info += f"You can view it at: {visualization_result.get('url')}"
                                        agent_result["response"] += viz_info
                                    
                                    # Add visualization data to the result
                                    agent_result["visualization"] = {
                                        "file_path": visualization_result.get("file_path"),
                                        "url": visualization_result.get("url"),
                                        "plot_type": analysis_result.get("plot_type")
                                    }
                except Exception as e:
                    logger.error(f"Error checking for visualization request: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            # Add agent result to workflow
            workflow["agent_result"] = agent_result
            
            # Step 5: Mathematical processing if needed
            self._update_workflow_step(workflow_id, "mathematical_processing", "Processing mathematical content")
            
            # Check if the input contains mathematical content
            contains_math = agent_result.get("contains_math", False)
            math_result = None
            
            if contains_math:
                # Extract the mathematical query
                math_query = agent_result.get("math_query")
                
                if not math_query:
                    # Try to extract from the response
                    response = agent_result.get("response", "")
                    
                    # In a real implementation, this would use better NLP to extract the query
                    # For this example, just use the response as the query
                    math_query = response
                
                # Process with math agent
                try:
                    # Find a suitable math agent
                    math_agent = self._get_agent("math_computation_agent")
                    
                    if math_agent:
                        # Prepare message for the math agent
                        math_message = {
                            "header": {
                                "message_id": str(uuid.uuid4()),
                                "sender": "workflow_engine",
                                "recipient": "math_computation_agent",
                                "timestamp": datetime.now().isoformat(),
                                "message_type": "math_computation"
                            },
                            "body": {
                                "query": math_query,
                                "input_type": processed_input.get("input_type", "text"),
                                "requires_explanation": True,
                                "conversation_id": workflow.get("conversation_id")
                            }
                        }
                        
                        # Process with math agent
                        math_result = math_agent.process_message(math_message)
                        workflow["math_result"] = math_result
                    else:
                        logger.warning("No suitable math agent found for computation")
                except Exception as e:
                    logger.error(f"Error in mathematical processing: {str(e)}")
                    math_result = {
                        "success": False,
                        "error": f"Mathematical processing failed: {str(e)}",
                        "query": math_query
                    }
                    workflow["math_result"] = math_result
            
            # Step 6: Generate final response
            self._update_workflow_step(workflow_id, "response_generation", "Generating final response")
            
            final_response = None
            
            if math_result and math_result.get("success", False):
                # Generate response with mathematical results
                if hasattr(self, 'llm_integration') and self.llm_integration:
                    final_response = self.llm_integration.process_with_mathematical_result(
                        processed_input,
                        math_result,
                        {"conversation_id": workflow.get("conversation_id")}
                    )
                else:
                    final_response = math_result
            else:
                # Use the initial response
                final_response = agent_result
            
            # Step 6.5: Generate visualizations if applicable
            visualizations = []
            
            # If math computation included a visualization, add it
            if math_result and "visualization" in math_result:
                visualizations.append(math_result["visualization"])
            
            # If we have agent-generated visualizations, add them
            if agent_result and "visualization" in agent_result:
                visualizations.append(agent_result["visualization"])
            
            # If we have a specific visualization result from earlier, add it
            if visualization_result and visualization_result.get("success", False):
                visualizations.append(visualization_result)
            
            # Add visualizations to final response
            if visualizations:
                final_response["visualizations"] = visualizations
            
            # Add to workflow
            workflow["final_response"] = final_response
            
            # Step 7: Finalize workflow
            self._update_workflow_step(workflow_id, "finalization", "Finalizing workflow")
            
            # If we had mathematical content, save the relevant data
            if contains_math and math_result and math_result.get("success", False):
                # Store mathematical data for future reference
                # This would be in a real implementation
                pass
            
            # Add to context
            context_id = workflow["context_id"]
            context = self.context_manager.get_context(context_id)
            
            if context:
                # Add input entity
                input_entity_id = self.context_manager.add_entity_to_context(
                    context_id,
                    {
                        "type": "input",
                        "content": processed_input,
                        "timestamp": datetime.now().isoformat()
                    },
                    processed_input.get("input_type", "text")
                )
                
                # Add response entity
                response_entity_id = self.context_manager.add_entity_to_context(
                    context_id,
                    {
                        "type": "response",
                        "content": final_response,
                        "timestamp": datetime.now().isoformat()
                    },
                    "text"
                )
                
                # Add relation between input and response
                if input_entity_id and response_entity_id:
                    self.context_manager.add_reference_to_context(
                        context_id,
                        input_entity_id,
                        response_entity_id,
                        "response_to"
                    )
            
            # Finalize workflow
            workflow["result"] = final_response
            workflow["state"] = "completed"
            workflow["updated_at"] = datetime.now().isoformat()
            
            logger.info(f"Workflow completed successfully: {workflow_id}")
            
        except Exception as e:
            logger.error(f"Error processing workflow {workflow_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Update workflow state
            workflow = self.active_workflows.get(workflow_id)
            if workflow:
                workflow["state"] = "error"
                workflow["error"] = str(e)
                workflow["updated_at"] = datetime.now().isoformat()
    
    def _update_workflow_step(self, workflow_id: str, step_name: str, description: str) -> None:
        """
        Update workflow with a new step.
        
        Args:
            workflow_id: Workflow identifier
            step_name: Step name
            description: Step description
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return
        
        # Add step
        workflow["steps"].append({
            "name": step_name,
            "description": description,
            "timestamp": datetime.now().isoformat()
        })
        
        # Update current step
        workflow["current_step"] = len(workflow["steps"])
        workflow["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"Workflow {workflow_id} - Step: {step_name}")

    def integrated_response(self, query: str, preferences: Optional[Dict[str, Any]] = None,
                           context_id: Optional[str] = None,
                           conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process an integrated response request combining mathematical, visualization, 
        and search capabilities.
        
        Args:
            query: The mathematical query to process
            preferences: Optional dictionary of user preferences:
                - include_steps: Whether to include step-by-step solutions
                - include_visualization: Whether to include visualizations
                - include_additional_context: Whether to include external context
            context_id: Optional context ID
            conversation_id: Optional conversation ID
            
        Returns:
            Dictionary containing the integrated response
        """
        start_time = time.time()
        
        # Initialize default preferences if not provided
        if preferences is None:
            preferences = {
                "include_steps": True,
                "include_visualization": True,
                "include_additional_context": True
            }
        
        # Start a new workflow with the query
        workflow_response = self.start_workflow({
            "content": query,
            "content_type": "text/plain",
            "preferences": preferences
        }, context_id, conversation_id)
        
        workflow_id = workflow_response.get("workflow_id")
        
        if not workflow_id:
            return {
                "success": False,
                "error": "Failed to start workflow",
                "response_text": "I'm sorry, I couldn't process your request due to a technical issue."
            }
        
        # Poll for workflow completion
        max_wait_time = 30  # Maximum wait time in seconds
        poll_interval = 0.5  # Time between polls in seconds
        
        total_wait_time = 0
        while total_wait_time < max_wait_time:
            status = self.get_workflow_status(workflow_id)
            
            if status.get("state") == "completed":
                # Workflow completed successfully
                result = self.get_workflow_result(workflow_id)
                
                if not result.get("success", False):
                    return {
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                        "response_text": "I'm sorry, I couldn't complete the processing of your request."
                    }
                
                # Get the result from the workflow
                workflow_result = result.get("result", {})
                
                # Format the integrated response
                execution_time = time.time() - start_time
                
                response = {
                    "response_id": workflow_id,
                    "response_text": workflow_result.get("response", ""),
                    "latex_expressions": workflow_result.get("latex_expressions", []),
                    "execution_time": round(execution_time, 2)
                }
                
                # Add optional components based on preferences
                if preferences.get("include_steps", True) and "steps" in workflow_result:
                    response["steps"] = workflow_result["steps"]
                
                if preferences.get("include_visualization", True) and "visualization_urls" in workflow_result:
                    response["visualization_urls"] = workflow_result["visualization_urls"]
                
                if preferences.get("include_additional_context", True) and "additional_context" in workflow_result:
                    response["additional_context"] = workflow_result["additional_context"]
                
                return response
            
            elif status.get("state") == "error":
                # Workflow encountered an error
                return {
                    "success": False,
                    "error": "Workflow encountered an error",
                    "response_text": "I'm sorry, an error occurred while processing your request."
                }
            
            # Wait before polling again
            time.sleep(poll_interval)
            total_wait_time += poll_interval
        
        # Timeout reached
        return {
            "success": False,
            "error": "Request timed out",
            "response_text": "I'm sorry, the processing of your request took too long and timed out."
        }

    def query_analysis(self, query: str, context_id: Optional[str] = None,
                      conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a mathematical query to identify required operations and agents.
        
        This endpoint performs detailed analysis of the query to determine:
        1. The mathematical operations needed (symbolic, numerical, etc.)
        2. The specific agents that should be activated to handle the query
        3. The structure of the query and any sub-problems it contains
        
        Args:
            query: The mathematical query to analyze
            context_id: Optional context ID
            conversation_id: Optional conversation ID
            
        Returns:
            Dictionary containing the analysis results
        """
        try:
            start_time = time.time()
            
            # Create context if needed
            if not context_id:
                context = self.context_manager.create_context(conversation_id)
                context_id = context.context_id
            
            # Ensure we have a core LLM agent available
            if not hasattr(self, 'core_llm_agent') or not self.core_llm_agent:
                self.core_llm_agent = self._get_agent("core_llm_agent")
                if self.core_llm_agent and not hasattr(self, 'llm_integration'):
                    self.llm_integration = MultimodalLLMIntegration(self.core_llm_agent)
                    logger.info("Successfully initialized LLM integration for query analysis")
            
            if not hasattr(self, 'llm_integration') or not self.llm_integration:
                return {
                    "success": False,
                    "error": "LLM integration not available for query analysis",
                    "query": query
                }
            
            # Process the input
            processed_input = self.input_processor.process_input(query, "text/plain")
            
            # Generate analysis prompt
            analysis_prompt = {
                "role": "system",
                "content": """Analyze the mathematical query and identify:
                1. Mathematical operations required (symbolic calculation, numerical computation, plotting, etc.)
                2. Mathematical concepts involved (algebra, calculus, statistics, etc.)
                3. Required specialized agents (math_computation_agent, visualization_agent, search_agent)
                4. Complexity level (simple, moderate, complex)
                5. Potential sub-problems that could be solved independently
                Format your response as a structured JSON object."""
            }
            
            # Send augmented query to LLM for analysis
            analysis_input = {
                "input_type": "text",
                "content": query,
                "analysis_prompt": analysis_prompt
            }
            
            # Get analysis from LLM
            analysis_result = self.llm_integration.process_multimodal_input(
                analysis_input,
                {
                    "conversation_id": conversation_id,
                    "context_id": context_id,
                    "mode": "analysis"
                }
            )
            
            if not analysis_result.get("success", False):
                return {
                    "success": False,
                    "error": analysis_result.get("error", "Unknown error during query analysis"),
                    "query": query
                }
            
            # Extract the structured analysis
            analysis = analysis_result.get("analysis", {})
            if not analysis:
                # Try to parse from response if not directly available
                try:
                    response = analysis_result.get("response", "")
                    # Extract JSON if present
                    import re
                    import json
                    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                    if json_match:
                        analysis = json.loads(json_match.group(1))
                    else:
                        # Simple parsing fallback
                        analysis = {
                            "operations": [],
                            "concepts": [],
                            "required_agents": [],
                            "complexity": "unknown",
                            "sub_problems": []
                        }
                        
                        if "symbolic" in response.lower():
                            analysis["operations"].append("symbolic_calculation")
                        if "numerical" in response.lower():
                            analysis["operations"].append("numerical_computation")
                        if "plot" in response.lower() or "graph" in response.lower():
                            analysis["operations"].append("plotting")
                            analysis["required_agents"].append("visualization_agent")
                        if "math" in response.lower() or "equation" in response.lower():
                            analysis["required_agents"].append("math_computation_agent")
                except Exception as e:
                    logger.error(f"Error parsing analysis response: {str(e)}")
                    analysis = {
                        "operations": [],
                        "concepts": [],
                        "required_agents": ["core_llm_agent"],
                        "complexity": "unknown",
                        "sub_problems": []
                    }
            
            # Add routing decision
            content_route = self.content_router.route_content(processed_input)
            
            # Merge routing information
            analysis["routing"] = {
                "primary_agent_type": content_route.get("agent_type", "core_llm"),
                "confidence": content_route.get("confidence", 0.0),
                "alternative_agents": content_route.get("alternative_agents", [])
            }
            
            # Add execution time
            execution_time = time.time() - start_time
            
            # Store analysis in context if available
            if context_id:
                try:
                    self.context_manager.add_entity_to_context(
                        context_id,
                        {
                            "type": "query_analysis",
                            "content": analysis,
                            "timestamp": datetime.now().isoformat()
                        },
                        "analysis"
                    )
                except Exception as e:
                    logger.warning(f"Failed to store analysis in context: {str(e)}")
            
            # Return analysis result
            return {
                "success": True,
                "query": query,
                "analysis": analysis,
                "execution_time": round(execution_time, 2)
            }
            
        except Exception as e:
            logger.error(f"Error in query analysis: {str(e)}")
            return {
                "success": False,
                "error": f"Error analyzing query: {str(e)}",
                "query": query
            }
