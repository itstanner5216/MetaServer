# explainer/explainer.py
"""
Phase 4: Retrieval Explainer/Selector for RAG System.

LLM-based chunk selection with human-readable explanations.
Uses an LLM to intelligently select the most relevant chunks from
retrieval candidates, providing rationales for auditability.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import litellm
except ImportError:
    litellm = None

from ..retrieval import RetrievalCandidate

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Data Types
# -----------------------------------------------------------------------------


@dataclass
class ExplainerOutput:
    """
    Structured output from the Retrieval Explainer.

    Contains the selected chunks, rationales, and metadata about
    the selection process for auditability and debugging.
    """

    selected_chunk_ids: List[str]  # 3-12 chunks selected by LLM
    rationales: Dict[str, str]  # chunk_id -> 1-2 sentence reason
    key_concepts: List[str]  # Extracted from query + chunks
    missing_context_requests: List[Dict[str, str]]  # {"topic": str, "reason": str}
    confidence_score: float  # 0-1 confidence in selection quality
    discarded_top: List[Dict[str, str]]  # {"chunk_id": str, "reason": str}
    token_count: int  # Approximate tokens used by selected chunks
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "selected_chunk_ids": self.selected_chunk_ids,
            "rationales": self.rationales,
            "key_concepts": self.key_concepts,
            "missing_context_requests": self.missing_context_requests,
            "confidence_score": self.confidence_score,
            "discarded_top": self.discarded_top,
            "token_count": self.token_count,
            "generated_at": self.generated_at.isoformat(),
        }

    @property
    def is_low_confidence(self) -> bool:
        """Check if confidence is below threshold for potential re-retrieval."""
        return self.confidence_score < 0.5

    @property
    def has_missing_context(self) -> bool:
        """Check if LLM flagged missing context."""
        return len(self.missing_context_requests) > 0

    @property
    def selection_count(self) -> int:
        """Number of chunks selected."""
        return len(self.selected_chunk_ids)


# -----------------------------------------------------------------------------
# System Prompt Template
# -----------------------------------------------------------------------------


SYSTEM_PROMPT = """You are a retrieval expert selecting the most relevant document chunks to answer a query.

Given:
- A user query
- A list of candidate chunks with IDs, scores, and snippets

Your task:
1. Select 3-12 chunks that best answer the query
2. Explain WHY each chunk is relevant (1-2 sentences)
3. Identify key concepts from the query and chunks
4. Note if important context is missing
5. Explain why you skipped high-scoring candidates (if any)

CRITICAL RULES:
- Only use chunk_ids from the provided list
- Never invent or hallucinate chunk_ids
- If no chunks are relevant, select the best available and note low confidence
- Prefer chunks that directly answer the query over tangentially related ones
- Consider diversity - avoid selecting highly redundant chunks

Output JSON format:
{
  "selected_chunk_ids": ["chunk-id-1", "chunk-id-2", ...],
  "rationales": {
    "chunk-id-1": "This chunk explains X which directly answers...",
    "chunk-id-2": "Contains the definition of Y mentioned in query..."
  },
  "key_concepts": ["concept1", "concept2"],
  "missing_context": [{"topic": "X", "reason": "Query asks about X but no chunks cover it"}],
  "confidence": 0.85,
  "discarded_top": [{"chunk_id": "high-scoring-id", "reason": "Off-topic despite high score"}]
}"""


USER_PROMPT_TEMPLATE = """Query: {query}

Candidate chunks (ranked by retrieval score):

{candidates}

Select the most relevant chunks for answering this query. Return valid JSON only."""


RETRY_PROMPT_TEMPLATE = """Your previous response was not valid JSON. Please try again.

Query: {query}

Candidate chunks (ranked by retrieval score):

{candidates}

Return ONLY valid JSON matching this schema:
{{
  "selected_chunk_ids": ["chunk-id-1", ...],
  "rationales": {{"chunk-id-1": "reason..."}},
  "key_concepts": ["concept1", ...],
  "missing_context": [{{"topic": "X", "reason": "..."}}],
  "confidence": 0.85,
  "discarded_top": [{{"chunk_id": "...", "reason": "..."}}]
}}"""


# -----------------------------------------------------------------------------
# Retrieval Explainer
# -----------------------------------------------------------------------------


class RetrievalExplainer:
    """
    LLM-based chunk selection with human-readable explanations.

    Uses an LLM to intelligently select the most relevant chunks
    from retrieval candidates, providing rationales for auditability.

    Key Features:
    - Selects 3-12 chunks from up to 30 candidates
    - Provides human-readable rationales for each selection
    - Extracts key concepts from query and chunks
    - Flags insufficient context for potential re-retrieval
    - Detects and rejects hallucinated chunk IDs
    - Uses low temperature (0.3) for deterministic selection

    Example:
        explainer = RetrievalExplainer(
            llm_client=litellm,
            model="gpt-4o-mini",
            temperature=0.3
        )
        result = explainer.select_chunks(
            query="How to read files in Python?",
            candidates=retrieval_candidates,
            token_budget=4000
        )
        print(result.rationales)
    """

    def __init__(
        self,
        llm_client: Any = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
        max_selected: int = 8,
        min_selected: int = 3,
        max_retries: int = 2,
    ):
        """
        Initialize the Retrieval Explainer.

        Args:
            llm_client: LLM client (litellm or compatible). If None, uses litellm.
            model: Model identifier for LLM calls (e.g., "gpt-4o-mini", "claude-3-haiku-20240307")
            temperature: Sampling temperature (0.3 for determinism)
            max_selected: Maximum chunks to select (default 8)
            min_selected: Minimum chunks to select (default 3)
            max_retries: Number of retries on invalid JSON response
        """
        if llm_client is None:
            if litellm is None:
                raise ImportError(
                    "litellm is required for RetrievalExplainer. "
                    "Install with: pip install litellm"
                )
            self.llm_client = litellm
        else:
            self.llm_client = llm_client

        self.model = model
        self.temperature = temperature
        self.max_selected = max_selected
        self.min_selected = min_selected
        self.max_retries = max_retries

        # Metrics
        self._selection_count = 0
        self._retry_count = 0
        self._validation_failures = 0

        logger.info(
            f"RetrievalExplainer initialized: model={model}, "
            f"temperature={temperature}, max_selected={max_selected}"
        )

    def select_chunks(
        self,
        query: str,
        candidates: List[RetrievalCandidate],
        token_budget: int = 4000,
    ) -> ExplainerOutput:
        """
        Select the most relevant chunks from candidates using LLM.

        Args:
            query: User's search query
            candidates: List of RetrievalCandidate from retrieval phase
            token_budget: Maximum tokens for selected chunks (approximate)

        Returns:
            ExplainerOutput with selected chunks, rationales, and metadata

        Raises:
            ValueError: If candidates list is empty
            RuntimeError: If LLM call fails after retries
        """
        if not candidates:
            raise ValueError("Candidates list cannot be empty")

        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        query = query.strip()

        # Build candidate lookup for validation
        candidate_lookup = {c.chunk_id: c for c in candidates}
        valid_chunk_ids = set(candidate_lookup.keys())

        logger.info(
            f"Selecting chunks: query='{query[:50]}...', "
            f"candidates={len(candidates)}, token_budget={token_budget}"
        )

        # Build prompts
        user_prompt = self._build_prompt(query, candidates)

        # Try LLM call with retries
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                # Use retry prompt after first attempt
                if attempt > 0:
                    self._retry_count += 1
                    prompt = self._build_retry_prompt(query, candidates)
                else:
                    prompt = user_prompt

                # Call LLM
                response = self._call_llm(prompt)

                # Parse response
                output = self._parse_response(response, candidates, valid_chunk_ids)

                # Validate output
                is_valid, error_msg = self._validate_output(output, candidates)

                if is_valid:
                    # Apply token budget constraints
                    output = self._apply_token_budget(output, candidate_lookup, token_budget)

                    self._selection_count += 1
                    logger.info(
                        f"Chunk selection complete: selected={output.selection_count}, "
                        f"confidence={output.confidence_score:.2f}"
                    )
                    return output
                else:
                    last_error = error_msg
                    logger.warning(
                        f"Validation failed (attempt {attempt + 1}): {error_msg}"
                    )
                    self._validation_failures += 1

            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                logger.warning(f"JSON parse failed (attempt {attempt + 1}): {e}")
                self._validation_failures += 1

            except Exception as e:
                last_error = f"LLM call error: {e}"
                logger.error(f"LLM call failed (attempt {attempt + 1}): {e}")

        # All retries exhausted - create fallback output
        logger.error(f"Selection failed after {self.max_retries + 1} attempts: {last_error}")
        return self._create_fallback_output(query, candidates, last_error)

    def _build_prompt(
        self,
        query: str,
        candidates: List[RetrievalCandidate],
    ) -> str:
        """
        Build the user prompt with query and candidate snippets.

        Args:
            query: User's search query
            candidates: Retrieval candidates

        Returns:
            Formatted user prompt string
        """
        # Format candidates with IDs, scores, and snippets
        candidate_lines = []
        for i, c in enumerate(candidates, 1):
            line = (
                f"[{i}] ID: {c.chunk_id}\n"
                f"    Score: {c.score:.4f} (semantic: {c.semantic_score:.4f}"
            )
            if c.bm25_score is not None:
                line += f", bm25: {c.bm25_score:.4f}"
            line += ")\n"
            line += f"    Path: {c.path}\n"
            line += f"    Risk: {c.risk_level} | Scope: {c.scope}\n"
            line += f"    Snippet: {c.snippet[:200]}..."
            candidate_lines.append(line)

        candidates_text = "\n\n".join(candidate_lines)

        return USER_PROMPT_TEMPLATE.format(
            query=query,
            candidates=candidates_text,
        )

    def _build_retry_prompt(
        self,
        query: str,
        candidates: List[RetrievalCandidate],
    ) -> str:
        """
        Build a cleaner retry prompt for JSON parsing errors.

        Args:
            query: User's search query
            candidates: Retrieval candidates

        Returns:
            Formatted retry prompt string
        """
        # Simpler candidate format for retry
        candidate_lines = []
        for c in candidates:
            line = f"- {c.chunk_id}: score={c.score:.3f}, snippet=\"{c.snippet[:100]}...\""
            candidate_lines.append(line)

        candidates_text = "\n".join(candidate_lines)

        return RETRY_PROMPT_TEMPLATE.format(
            query=query,
            candidates=candidates_text,
        )

    def _call_llm(self, user_prompt: str) -> str:
        """
        Call the LLM with the prompts.

        Args:
            user_prompt: The user prompt with query and candidates

        Returns:
            LLM response text

        Raises:
            RuntimeError: If LLM call fails
        """
        try:
            # Prepare messages
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            # Prepare kwargs
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
            }

            # Add response_format if model supports it (OpenAI models)
            if "gpt" in self.model.lower() or "o1" in self.model.lower():
                kwargs["response_format"] = {"type": "json_object"}

            # Call LLM via litellm
            response = self.llm_client.completion(**kwargs)

            # Extract content
            content = response.choices[0].message.content
            return content

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _parse_response(
        self,
        response: str,
        candidates: List[RetrievalCandidate],
        valid_chunk_ids: set,
    ) -> ExplainerOutput:
        """
        Parse LLM JSON response and validate chunk IDs.

        Args:
            response: Raw LLM response text
            candidates: Original candidates for token counting
            valid_chunk_ids: Set of valid chunk IDs from candidates

        Returns:
            ExplainerOutput parsed from response

        Raises:
            json.JSONDecodeError: If response is not valid JSON
            KeyError: If required fields are missing
        """
        # Clean response - extract JSON if wrapped in markdown
        response = response.strip()
        if response.startswith("```"):
            # Extract JSON from markdown code block
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
            if match:
                response = match.group(1)
            else:
                # Try removing just the first and last lines
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines)

        # Parse JSON
        data = json.loads(response)

        # Extract selected chunk IDs
        selected_ids = data.get("selected_chunk_ids", [])

        # Validate and filter to only valid IDs (hallucination detection)
        valid_selected = []
        hallucinated = []
        for chunk_id in selected_ids:
            if chunk_id in valid_chunk_ids:
                valid_selected.append(chunk_id)
            else:
                hallucinated.append(chunk_id)
                logger.warning(f"Detected hallucinated chunk_id: {chunk_id}")

        if hallucinated:
            logger.warning(
                f"Filtered {len(hallucinated)} hallucinated chunk IDs: {hallucinated}"
            )

        # Extract rationales (only for valid IDs)
        raw_rationales = data.get("rationales", {})
        rationales = {
            k: v for k, v in raw_rationales.items()
            if k in valid_chunk_ids
        }

        # Extract other fields
        key_concepts = data.get("key_concepts", [])
        if not isinstance(key_concepts, list):
            key_concepts = []

        missing_context = data.get("missing_context", [])
        if not isinstance(missing_context, list):
            missing_context = []

        confidence = data.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        discarded_top = data.get("discarded_top", [])
        if not isinstance(discarded_top, list):
            discarded_top = []

        # Calculate token count for selected chunks
        token_count = self._estimate_tokens(valid_selected, candidates)

        return ExplainerOutput(
            selected_chunk_ids=valid_selected,
            rationales=rationales,
            key_concepts=key_concepts,
            missing_context_requests=missing_context,
            confidence_score=confidence,
            discarded_top=discarded_top,
            token_count=token_count,
        )

    def _validate_output(
        self,
        output: ExplainerOutput,
        candidates: List[RetrievalCandidate],
    ) -> Tuple[bool, str]:
        """
        Validate the parsed output.

        Args:
            output: Parsed ExplainerOutput
            candidates: Original candidates

        Returns:
            Tuple of (is_valid, error_message)
        """
        valid_ids = {c.chunk_id for c in candidates}

        # Check all selected chunk_ids exist
        for chunk_id in output.selected_chunk_ids:
            if chunk_id not in valid_ids:
                return False, f"Invalid chunk_id: {chunk_id}"

        # Check selected count is within bounds
        count = len(output.selected_chunk_ids)
        if count < self.min_selected:
            # Allow fewer if total candidates is less than min
            if len(candidates) >= self.min_selected:
                return False, f"Selected {count} chunks, minimum is {self.min_selected}"

        if count > self.max_selected:
            return False, f"Selected {count} chunks, maximum is {self.max_selected}"

        # Check confidence is 0-1
        if not 0.0 <= output.confidence_score <= 1.0:
            return False, f"Confidence {output.confidence_score} not in [0, 1]"

        return True, ""

    def _estimate_tokens(
        self,
        chunk_ids: List[str],
        candidates: List[RetrievalCandidate],
    ) -> int:
        """
        Estimate token count for selected chunks.

        Uses rough approximation: ~4 characters per token.

        Args:
            chunk_ids: Selected chunk IDs
            candidates: Original candidates with snippets

        Returns:
            Estimated token count
        """
        id_to_candidate = {c.chunk_id: c for c in candidates}

        total_chars = 0
        for chunk_id in chunk_ids:
            if chunk_id in id_to_candidate:
                # Use snippet length as proxy (actual text would be longer)
                # Multiply by 3 to estimate full text from snippet
                snippet_len = len(id_to_candidate[chunk_id].snippet)
                total_chars += snippet_len * 3

        # Approximate tokens (4 chars per token average for English)
        return total_chars // 4

    def _apply_token_budget(
        self,
        output: ExplainerOutput,
        candidate_lookup: Dict[str, RetrievalCandidate],
        token_budget: int,
    ) -> ExplainerOutput:
        """
        Trim selected chunks if they exceed token budget.

        Keeps highest-scored chunks that fit within budget.

        Args:
            output: Parsed ExplainerOutput
            candidate_lookup: Mapping of chunk_id to candidate
            token_budget: Maximum token budget

        Returns:
            ExplainerOutput with chunks trimmed to budget
        """
        if output.token_count <= token_budget:
            return output

        logger.info(
            f"Token budget exceeded ({output.token_count} > {token_budget}), trimming"
        )

        # Sort selected chunks by score (descending)
        scored_ids = [
            (chunk_id, candidate_lookup[chunk_id].score)
            for chunk_id in output.selected_chunk_ids
            if chunk_id in candidate_lookup
        ]
        scored_ids.sort(key=lambda x: x[1], reverse=True)

        # Keep chunks until budget is exhausted
        kept_ids = []
        cumulative_tokens = 0

        for chunk_id, _ in scored_ids:
            candidate = candidate_lookup.get(chunk_id)
            if not candidate:
                continue

            # Estimate tokens for this chunk
            chunk_tokens = len(candidate.snippet) * 3 // 4

            if cumulative_tokens + chunk_tokens <= token_budget:
                kept_ids.append(chunk_id)
                cumulative_tokens += chunk_tokens

            if len(kept_ids) >= self.min_selected and cumulative_tokens >= token_budget * 0.8:
                # Stop when we have minimum and are near budget
                break

        # Ensure minimum selection
        if len(kept_ids) < self.min_selected:
            for chunk_id, _ in scored_ids:
                if chunk_id not in kept_ids:
                    kept_ids.append(chunk_id)
                if len(kept_ids) >= self.min_selected:
                    break

        # Update rationales to only include kept chunks
        kept_rationales = {
            k: v for k, v in output.rationales.items()
            if k in kept_ids
        }

        # Recalculate token count
        new_token_count = sum(
            len(candidate_lookup[cid].snippet) * 3 // 4
            for cid in kept_ids
            if cid in candidate_lookup
        )

        logger.info(f"Trimmed to {len(kept_ids)} chunks, ~{new_token_count} tokens")

        return ExplainerOutput(
            selected_chunk_ids=kept_ids,
            rationales=kept_rationales,
            key_concepts=output.key_concepts,
            missing_context_requests=output.missing_context_requests,
            confidence_score=output.confidence_score,
            discarded_top=output.discarded_top,
            token_count=new_token_count,
            generated_at=output.generated_at,
        )

    def _create_fallback_output(
        self,
        query: str,
        candidates: List[RetrievalCandidate],
        error: str,
    ) -> ExplainerOutput:
        """
        Create fallback output when LLM selection fails.

        Falls back to top candidates by score with low confidence.

        Args:
            query: Original query
            candidates: Retrieval candidates
            error: Error message from failed attempts

        Returns:
            ExplainerOutput with top candidates and low confidence
        """
        logger.warning(f"Using fallback selection due to: {error}")

        # Sort by score and take top candidates
        sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
        selected = sorted_candidates[:self.min_selected]

        selected_ids = [c.chunk_id for c in selected]
        rationales = {
            c.chunk_id: f"Fallback selection: highest scoring candidate (score={c.score:.3f})"
            for c in selected
        }

        token_count = sum(len(c.snippet) * 3 // 4 for c in selected)

        return ExplainerOutput(
            selected_chunk_ids=selected_ids,
            rationales=rationales,
            key_concepts=[],
            missing_context_requests=[{
                "topic": "LLM Selection",
                "reason": f"LLM-based selection failed: {error}. Using score-based fallback."
            }],
            confidence_score=0.3,  # Low confidence for fallback
            discarded_top=[],
            token_count=token_count,
        )

    def get_metrics(self) -> Dict:
        """
        Get explainer metrics.

        Returns:
            Dict with selection statistics
        """
        return {
            "selection_count": self._selection_count,
            "retry_count": self._retry_count,
            "validation_failures": self._validation_failures,
            "model": self.model,
            "temperature": self.temperature,
            "max_selected": self.max_selected,
            "min_selected": self.min_selected,
        }


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


def create_explainer(
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    **kwargs,
) -> RetrievalExplainer:
    """
    Create a RetrievalExplainer with default settings.

    Args:
        model: LLM model to use
        temperature: Sampling temperature
        **kwargs: Additional arguments for RetrievalExplainer

    Returns:
        Configured RetrievalExplainer instance
    """
    return RetrievalExplainer(
        model=model,
        temperature=temperature,
        **kwargs,
    )
