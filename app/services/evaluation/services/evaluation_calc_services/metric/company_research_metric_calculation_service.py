"""
Company Research Metric Calculation Service.

This service implements the company research metric calculation based on one criteria:
1. Has Done Research - Does the candidate seamlessly integrate specific details about the company, 
   its products, or its culture into their answers, showing they've done their homework?

The service uses LLM APIs to analyze dialog sections and generate sub-metrics,
calculate scores, and provide revision suggestions.
"""
import json
from app.services.evaluation.utils.litellm_client import acompletion
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
from pydantic import BaseModel

from app.services.evaluation.business import (
    MetricCalculationService,
    DialogSection, 
    Metric,
    MetricGroup,
    Score, 
    ScoreLabel,
    MetricMetadata,
    ScoreTransformationService,
    Logger,
    IdGenerator
)


class CompanyResearchSubMetrics(BaseModel):
    """
    Internal data structure for company research sub-metrics.
    Field names are aligned with LLM prompts to avoid conversion.
    This is only used within the service implementation.
    """
    # Fields that come directly from LLM response
    has_done_research: bool
    company_details_mentioned: List[str] = []
    
    model_config = {"frozen": True}


class CompanyResearchMetricCalculationService(MetricCalculationService):
    """
    Company research metric calculation service implementation.
    
    Evaluates candidate responses based on:
    - Has done research on the company
    """
    
    def __init__(
        self, 
        logger: Logger, 
        id_generator: IdGenerator,
        score_transformation_service: ScoreTransformationService,
        model: str = "gpt-4o", 
        enable_revision: bool = False,
        eval_system_prompt_path: Optional[str] = None,
        eval_user_prompt_path: Optional[str] = None,
        revise_system_prompt_path: Optional[str] = None,
        revise_user_prompt_path: Optional[str] = None
    ):
        """
        Initialize the service.
        
        Args:
            logger: Logger instance for logging operations
            id_generator: ID generator for creating unique metric IDs
            score_transformation_service: Service for transforming between score labels and numeric scores
            model: LLM model to use for evaluation (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            enable_revision: Whether to generate revision suggestions (default: False)
            eval_system_prompt_path: Full path to custom evaluation system prompt file (optional)
            eval_user_prompt_path: Full path to custom evaluation user prompt file (optional)
            revise_system_prompt_path: Full path to custom revision system prompt file (optional)
            revise_user_prompt_path: Full path to custom revision user prompt file (optional)
        """
        self.logger = logger
        self.id_generator = id_generator
        self.score_transformation_service = score_transformation_service
        self.model = model
        self.temperature = 0.3
        self.enable_revision = enable_revision
        
        # Store custom prompt paths (full paths)
        self.custom_eval_system_prompt_path = eval_system_prompt_path
        self.custom_eval_user_prompt_path = eval_user_prompt_path
        self.custom_revise_system_prompt_path = revise_system_prompt_path
        self.custom_revise_user_prompt_path = revise_user_prompt_path
        
        # LiteLLM will automatically read API keys from environment variables
        
        # Load prompts
        self._load_prompts()
    
    async def create_metric_group(
        self, 
        dialog_sections: List[DialogSection], 
        metadata: MetricMetadata
    ) -> MetricGroup:
        """
        Create a complete MetricGroup entity for company research evaluation.
        
        Args:
            dialog_sections: The dialog sections to analyze
            metadata: The metric metadata 
            
        Returns:
            MetricGroup: Complete metric group with metrics for each section
        """
        try:
            self.logger.info("Creating company research metric group", {
                "dialog_sections_count": len(dialog_sections),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            # Process all dialog sections in a single LLM API call
            all_section_results = await self._generate_sub_metrics_for_all_sections(dialog_sections)
            
            # Calculate scores for all sections and prepare revision data
            sections_needing_revision = []
            section_scores = []
            section_sub_metrics = []
            
            for i, dialog_section in enumerate(dialog_sections):
                sub_metrics = all_section_results[i]
                score = self._calculate_score(sub_metrics)
                
                section_scores.append(score)
                section_sub_metrics.append(sub_metrics)
                
                # Collect sections that need revision (Poor scores)
                if score.score_label != ScoreLabel.GOOD:
                    sections_needing_revision.append((i, dialog_section, sub_metrics, score))
            
            # Generate revisions for all sections needing them in a single API call (if enabled)
            all_revisions = []
            if self.enable_revision and sections_needing_revision:
                all_revisions = await self._generate_revisions_for_all_sections(sections_needing_revision)
            
            # Create metrics from the batch results
            metrics = []
            revision_index = 0
            
            for i, dialog_section in enumerate(dialog_sections):
                # Generate unique metric ID for each section
                metric_id = self.id_generator.generate()
                
                self.logger.info("Processing dialog section result for company research", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "service": "CompanyResearchMetricCalculationService"
                })
                
                # Get data for this specific section from batch results
                sub_metrics = section_sub_metrics[i]
                score = section_scores[i]
                
                # Get revision (either from batch results or empty string)
                if not self.enable_revision or score.score_label == ScoreLabel.GOOD:
                    revision = ""
                else:
                    revision = all_revisions[revision_index] if revision_index < len(all_revisions) else ""
                    revision_index += 1
                
                # Convert internal sub-metrics to dictionary
                sub_metrics_dict = self._convert_sub_metrics_to_dict(sub_metrics)
                
                # Create metric entity for this section
                metric = Metric(
                    id=metric_id,
                    metadata=metadata,
                    dialog_section_id=dialog_section.id,
                    dialog_section_index=dialog_section.section_index,
                    sub_metrics=sub_metrics_dict,
                    score=score,
                    revision=revision
                )
                
                metrics.append(metric)
                
                self.logger.info("Successfully created company research metric for section", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "score_label": score.score_label.value,
                    "numeric_score": score.numeric_score,
                    "has_revision": bool(revision),
                    "service": "CompanyResearchMetricCalculationService"
                })
            
            # Create metric group
            metric_group = MetricGroup(
                metric_type=metadata.metric_type,
                metrics=metrics
            )
            
            self.logger.info("Successfully created company research metric group", {
                "dialog_sections_count": len(dialog_sections),
                "metrics_count": len(metrics),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            return metric_group
            
        except Exception as e:
            self.logger.error("Failed to create company research metric group", e, {
                "dialog_sections_count": len(dialog_sections),
                "service": "CompanyResearchMetricCalculationService"
            })
            raise
    
    def _load_prompts(self) -> None:
        """Load prompt templates from files."""
        try:
            # Default prompt directory
            default_prompt_dir = Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "prompts" / "evaluation" / "v1"
            
            # Load evaluation prompts with custom paths if provided, otherwise use defaults
            if self.custom_eval_system_prompt_path:
                eval_system_path = Path(self.custom_eval_system_prompt_path)
            else:
                eval_system_path = default_prompt_dir / "prompt_company_research_eval_system_msg.md"
                
            if self.custom_eval_user_prompt_path:
                eval_user_path = Path(self.custom_eval_user_prompt_path)
            else:
                eval_user_path = default_prompt_dir / "prompt_eval_user_msg.md"
                
            if self.custom_revise_system_prompt_path:
                revise_system_path = Path(self.custom_revise_system_prompt_path)
            else:
                revise_system_path = default_prompt_dir / "prompt_company_research_revise_system_msg.md"
                
            if self.custom_revise_user_prompt_path:
                revise_user_path = Path(self.custom_revise_user_prompt_path)
            else:
                revise_user_path = default_prompt_dir / "prompt_revise_user_msg.md"
            
            with open(eval_system_path, 'r', encoding='utf-8') as f:
                self.eval_system_prompt = f.read()
            
            with open(eval_user_path, 'r', encoding='utf-8') as f:
                self.eval_user_prompt = f.read()
            
            # Load revision prompts  
            with open(revise_system_path, 'r', encoding='utf-8') as f:
                self.revise_system_prompt = f.read()
            
            with open(revise_user_path, 'r', encoding='utf-8') as f:
                self.revise_user_prompt = f.read()
                
            self.logger.info("Company research prompts loaded successfully", {
                "service": "CompanyResearchMetricCalculationService",
                "custom_prompts": {
                    "eval_system": str(eval_system_path),
                    "eval_user": str(eval_user_path),
                    "revise_system": str(revise_system_path),
                    "revise_user": str(revise_user_path)
                }
            })
        except Exception as e:
            self.logger.error("Failed to load company research prompts", e, {
                "service": "CompanyResearchMetricCalculationService"
            })
            raise
    
    async def _generate_sub_metrics_for_all_sections(self, dialog_sections: List[DialogSection]) -> List[CompanyResearchSubMetrics]:
        """
        Generate sub-metrics for all dialog sections in a single LLM API call.
        
        Args:
            dialog_sections: List of dialog sections to analyze
            
        Returns:
            List[CompanyResearchSubMetrics]: List containing evaluation results for each section
        """
        try:
            self.logger.info("Generating company research sub-metrics for all sections", {
                "dialog_sections_count": len(dialog_sections),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            # Format all dialog sections for LLM
            all_sections_json = []
            for dialog_section in dialog_sections:
                messages_json = []
                for msg in dialog_section.messages:
                    messages_json.append({
                        "role": msg.role.value.lower(),
                        "start_time": msg.start_time.timestamp(),
                        "end_time": msg.end_time.timestamp(),
                        "speakerId": 0 if msg.role.value == "CANDIDATE" else None,
                        "content": msg.content
                    })
                
                section_json = {
                    "section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "messages": messages_json
                }
                all_sections_json.append(section_json)
            
            # Prepare user prompt for all sections
            user_content = self.eval_user_prompt.format(
                dialog_sections=json.dumps(all_sections_json, ensure_ascii=False, indent=2)
            )
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.eval_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            # Process results for each section
            section_results = []
            
            # Handle different response formats from LLM
            if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                # Expected case: LLM returned {"results": [array]} 
                result_list = result["results"]
                if len(result_list) != len(dialog_sections):
                    error_msg = f"Expected {len(dialog_sections)} section results, got {len(result_list)} results in wrapped array"
                    raise ValueError(error_msg)
                self.logger.info("LLM returned expected dictionary format with results array", {
                    "dialog_sections_count": len(dialog_sections),
                    "results_count": len(result_list),
                    "service": "CompanyResearchMetricCalculationService"
                })
            elif isinstance(result, list) and len(result) == len(dialog_sections):
                # Legacy fallback case: LLM returned raw array
                self.logger.warning("LLM returned legacy array format instead of dictionary", None, {
                    "dialog_sections_count": len(dialog_sections),
                    "service": "CompanyResearchMetricCalculationService"
                })
                result_list = result
            elif isinstance(result, dict) and len(dialog_sections) == 1:
                # Fallback case: LLM returned single object for single section
                self.logger.warning("LLM returned single object instead of dictionary format for single section", None, {
                    "dialog_sections_count": len(dialog_sections),
                    "service": "CompanyResearchMetricCalculationService"
                })
                result_list = [result]
            else:
                # Error case: unexpected response format
                if isinstance(result, list):
                    error_msg = f"Expected {len(dialog_sections)} section results, got {len(result)} array elements in wrong format"
                elif isinstance(result, dict) and "results" in result:
                    error_msg = f"Expected {len(dialog_sections)} section results, got wrapped results with wrong format"
                else:
                    error_msg = f"Expected {len(dialog_sections)} section results, got unexpected format: {type(result).__name__}"
                raise ValueError(error_msg)
                
            # Process each result
            for i, section_result in enumerate(result_list):
                dialog_section = dialog_sections[i]
                
                # Validate section_index matches expected (if present)
                expected_section_index = dialog_section.section_index
                actual_section_index = section_result.get("section_index")
                if actual_section_index is not None and actual_section_index != expected_section_index:
                    self.logger.warning("Section index mismatch in evaluation result", None, {
                        "expected_index": expected_section_index,
                        "actual_index": actual_section_index,
                        "dialog_section_id": dialog_section.id,
                        "service": "CompanyResearchMetricCalculationService"
                    })
                
                # Use Pydantic's model_validate to parse LLM response
                sub_metrics = CompanyResearchSubMetrics.model_validate(section_result)
                section_results.append(sub_metrics)
            
            self.logger.info("Successfully generated company research sub-metrics for all sections", {
                "dialog_sections_count": len(dialog_sections),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            return section_results
            
        except Exception as e:
            self.logger.error("Failed to generate company research sub-metrics for all sections", e, {
                "dialog_sections_count": len(dialog_sections),
                "service": "CompanyResearchMetricCalculationService"
            })
            raise
    
    async def _generate_revisions_for_all_sections(self, sections_needing_revision: List[Tuple[int, DialogSection, CompanyResearchSubMetrics, Score]]) -> List[str]:
        """
        Generate revisions for all sections needing them in a single LLM API call.
        
        Args:
            sections_needing_revision: List of tuples (index, dialog_section, sub_metrics, score)
            
        Returns:
            List[str]: List of revision texts in the same order as input
        """
        if not sections_needing_revision:
            return []
            
        try:
            self.logger.info("Generating company research revisions for all sections", {
                "sections_count": len(sections_needing_revision),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            # Format all sections needing revision for LLM
            all_revision_data = []
            for _, dialog_section, sub_metrics, score in sections_needing_revision:
                # Format dialog section
                section_messages = []
                for msg in dialog_section.messages:
                    section_messages.append({
                        "role": msg.role.value.lower(),
                        "content": msg.content
                    })
                
                section_data = {
                    "section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "messages": section_messages
                }
                
                # Prepare evaluation data
                evaluation_data = self._prepare_evaluation_data(sub_metrics, score)
                
                revision_item = {
                    "dialog_section": section_data,
                    "evaluation": evaluation_data
                }
                all_revision_data.append(revision_item)
            
            # Prepare revision prompt for all sections
            user_content = self.revise_user_prompt.format(
                revision_data=json.dumps(all_revision_data, ensure_ascii=False, indent=2)
            )
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.revise_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            # Process revision results
            # Handle different response formats from LLM
            if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                # Expected case: LLM returned {"results": [array]}
                revision_list = result["results"]
                if len(revision_list) != len(sections_needing_revision):
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got {len(revision_list)} results in wrapped array"
                    raise ValueError(error_msg)
                self.logger.info("LLM returned expected dictionary format for revisions", {
                    "sections_count": len(sections_needing_revision),
                    "results_count": len(revision_list),
                    "service": "CompanyResearchMetricCalculationService"
                })
            elif isinstance(result, list) and len(result) == len(sections_needing_revision):
                # Legacy fallback case: LLM returned raw array
                self.logger.warning("LLM returned legacy array format for revisions", None, {
                    "sections_count": len(sections_needing_revision),
                    "service": "CompanyResearchMetricCalculationService"
                })
                revision_list = result
            else:
                # Error case: unexpected response format
                if isinstance(result, list):
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got {len(result)} array elements"
                elif isinstance(result, dict) and "results" in result:
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got wrapped results with wrong format"
                else:
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got unexpected format: {type(result).__name__}"
                raise ValueError(error_msg)
                
            # Process each revision result
            revisions = []
            for i, revision_result in enumerate(revision_list):
                if isinstance(revision_result, dict):
                    # Validate section_index if present
                    if "section_index" in revision_result:
                        expected_section_index = sections_needing_revision[i][1].section_index
                        actual_section_index = revision_result["section_index"]
                        if actual_section_index != expected_section_index:
                            self.logger.warning("Section index mismatch in revision result", None, {
                                "expected_index": expected_section_index,
                                "actual_index": actual_section_index,
                                "revision_item_index": i,
                                "service": "CompanyResearchMetricCalculationService"
                            })
                    
                    if "revised_speech" in revision_result:
                        revised_speech = revision_result["revised_speech"]
                        revisions.append(revised_speech if revised_speech is not None else "")
                    else:
                        revisions.append("")
                else:
                    revisions.append("")
            
            self.logger.info("Successfully generated company research revisions for all sections", {
                "sections_count": len(sections_needing_revision),
                "revisions_generated": len([r for r in revisions if r]),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            return revisions
                
        except Exception as e:
            self.logger.error("Failed to generate company research revisions for all sections", e, {
                "sections_count": len(sections_needing_revision),
                "service": "CompanyResearchMetricCalculationService"
            })
            raise
    
    async def _generate_sub_metrics(self, dialog_section: DialogSection) -> CompanyResearchSubMetrics:
        """
        Generate sub-metrics for company research evaluation using LLM API.
        
        Args:
            dialog_section: The dialog section to analyze
            
        Returns:
            CompanyResearchSubMetrics containing evaluation results
        """
        try:
            self.logger.info("Generating company research sub-metrics", {
                "dialog_section_id": dialog_section.id,
                "service": "CompanyResearchMetricCalculationService"
            })
            
            # Format dialog section for LLM
            messages_json = []
            for msg in dialog_section.messages:
                messages_json.append({
                    "role": msg.role.value.lower(),
                    "start_time": msg.start_time.timestamp(),
                    "end_time": msg.end_time.timestamp(),
                    "speakerId": 0 if msg.role.value == "CANDIDATE" else None,
                    "content": msg.content
                })
            
            dialog_section_json = {
                "section_id": dialog_section.id,
                "section_index": dialog_section.section_index,
                "messages": messages_json
            }
            
            # Prepare user prompt
            user_content = self.eval_user_prompt.format(dialog_sections=json.dumps([dialog_section_json], ensure_ascii=False, indent=2))
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.eval_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            # Handle response format (should be array with single section)
            if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                section_result = result["results"][0]
            elif isinstance(result, list):
                section_result = result[0]
            else:
                section_result = result
            
            # Use Pydantic's model_validate to parse LLM response directly
            sub_metrics = CompanyResearchSubMetrics.model_validate(section_result)
            
            self.logger.info("Successfully generated company research sub-metrics", {
                "dialog_section_id": dialog_section.id,
                "service": "CompanyResearchMetricCalculationService",
                "has_done_research": sub_metrics.has_done_research,
                "company_details_count": len(sub_metrics.company_details_mentioned)
            })
            
            return sub_metrics
            
        except Exception as e:
            self.logger.error("Failed to generate company research sub-metrics", e, {
                "dialog_section_id": dialog_section.id,
                "service": "CompanyResearchMetricCalculationService"
            })
            raise
    
    def _calculate_score(self, sub_metrics: CompanyResearchSubMetrics) -> Score:
        """
        Calculate company research score based on sub-metrics.
        
        Scoring logic based on the prompt rubric:
        - Poor: Fails to mention any specific company details when the question provides an opportunity to do so
        - Good: Effectively incorporates specific company details into their response, or the question does not pertain to the company
        
        Args:
            sub_metrics: CompanyResearchSubMetrics from _generate_sub_metrics
            
        Returns:
            Score object with label and numeric value
        """
        try:
            self.logger.info("Calculating company research score", {
                "has_done_research": sub_metrics.has_done_research,
                "company_details_count": len(sub_metrics.company_details_mentioned),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            # Apply scoring rubric
            if sub_metrics.has_done_research:
                score_label = ScoreLabel.GOOD
            else:
                score_label = ScoreLabel.POOR
            
            # Use transformation service to create consistent score
            score = self.score_transformation_service.create_score(score_label)
            
            self.logger.info("Successfully calculated company research score", {
                "score_label": score.score_label.value,
                "numeric_score": score.numeric_score,
                "has_done_research": sub_metrics.has_done_research,
                "company_details_count": len(sub_metrics.company_details_mentioned),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            return score
            
        except Exception as e:
            self.logger.error("Failed to calculate company research score", e, {
                "service": "CompanyResearchMetricCalculationService"
            })
            raise
    
    async def _generate_revision(self, sub_metrics: CompanyResearchSubMetrics, score: Score, dialog_section: DialogSection) -> str:
        """
        Generate revision text for company research improvement using LLM API.
        
        Args:
            sub_metrics: CompanyResearchSubMetrics from _generate_sub_metrics
            score: Calculated score
            dialog_section: Original dialog section
            
        Returns:
            Revision text or empty string for Good scores or when revision is disabled
        """
        try:
            self.logger.info("Generating company research revision", {
                "dialog_section_id": dialog_section.id,
                "score_label": score.score_label.value,
                "enable_revision": self.enable_revision,
                "service": "CompanyResearchMetricCalculationService"
            })
            
            # No revision if disabled or for Good scores
            if not self.enable_revision or score.score_label == ScoreLabel.GOOD:
                self.logger.info("No revision needed - disabled or Good score", {
                    "dialog_section_id": dialog_section.id,
                    "enable_revision": self.enable_revision,
                    "score_label": score.score_label.value,
                    "service": "CompanyResearchMetricCalculationService"
                })
                return ""
            
            # Prepare evaluation data for revision prompt
            evaluation_data = self._prepare_evaluation_data(sub_metrics, score)
            
            # Format dialog section
            section_messages: List[Dict[str, str]] = []
            for msg in dialog_section.messages:
                section_messages.append({
                    "role": msg.role.value.lower(),
                    "content": msg.content
                })
            
            section_data: Dict[str, Any] = {
                "section_id": dialog_section.id,
                "section_index": dialog_section.section_index,
                "messages": section_messages
            }
            
            # Prepare revision data
            revision_data = [{
                "dialog_section": section_data,
                "evaluation": evaluation_data
            }]
            
            # Prepare revision prompt
            user_content = self.revise_user_prompt.format(
                revision_data=json.dumps(revision_data, ensure_ascii=False, indent=2)
            )
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.revise_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            # Handle response format (should be array with single section)
            if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                revision_result = result["results"][0]
            elif isinstance(result, list):
                revision_result = result[0]
            else:
                revision_result = result
            
            # Process revision results
            if isinstance(revision_result, dict) and "revised_speech" in revision_result:
                revision = revision_result["revised_speech"] or ""
            else:
                revision = ""
            
            self.logger.info("Successfully generated company research revision", {
                "dialog_section_id": dialog_section.id,
                "revision_length": len(revision),
                "service": "CompanyResearchMetricCalculationService"
            })
            
            return revision
            
        except Exception as e:
            self.logger.error("Failed to generate company research revision", e, {
                "dialog_section_id": dialog_section.id,
                "service": "CompanyResearchMetricCalculationService"
            })
            raise
    
    def _prepare_evaluation_data(self, sub_metrics: CompanyResearchSubMetrics, score: Score) -> Dict[str, Any]:
        """Prepare evaluation data for revision prompt."""
        # Use Pydantic's model_dump() to serialize sub-metrics
        data = sub_metrics.model_dump()
        
        # Add score information
        data["score_label"] = score.score_label.value
        
        return data
    
    def _convert_sub_metrics_to_dict(self, sub_metrics: CompanyResearchSubMetrics) -> Dict[str, Any]:
        """Convert internal CompanyResearchSubMetrics to dictionary format for Metric entity."""
        # Use Pydantic's model_dump() to serialize to dictionary - all fields are already included
        return sub_metrics.model_dump()
    
    async def _call_llm_with_json_response(self, messages: List[Dict[str, str]]) -> Any:
        """
        Helper method to call LiteLLM and parse JSON response.
        
        Args:
            messages: List of message dictionaries for the LLM
            
        Returns:
            Parsed JSON response as dictionary
        """
        try:
            # Note: LiteLLM doesn't have comprehensive type stubs yet
            response = await acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                response_format={"type": "json_object"},  # Force JSON output
            )
            
            # Extract content and parse as JSON
            content = response.choices[0].message.content  # type: ignore
            if isinstance(content, str):
                return json.loads(content)
            else:
                raise ValueError("Unexpected response content type - expected string")
                
        except Exception as e:
            self.logger.error("LiteLLM API call failed", e, {
                "model": self.model,
                "service": "CompanyResearchMetricCalculationService"
            })
            raise