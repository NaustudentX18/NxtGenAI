#!/usr/bin/env python3
# =============================================================================
# PentestGPT-lite — AI Core (ReAct Reasoning Loop)
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# Implements the Thought → Action → Observation → Next loop (ReAct pattern).
#
# Architecture:
#   1. User task arrives as a natural-language string.
#   2. LLM generates a Thought (reasoning) + Action (tool name + args).
#   3. The requested tool is executed; output = Observation.
#   4. Observation is appended to the prompt context; loop continues.
#   5. Loop terminates when LLM outputs "DONE" or risk threshold exceeded.
#
# Risk Scoring (1–10):
#   Each proposed action is scored by a second lightweight prompt.
#   Actions scoring above config[security][max_risk_score] are skipped.
#   This prevents the AI from autonomously running destructive exploits.
#
# Memory constraint:
#   Context window is capped at 512 tokens (config.ini: llm.n_ctx).
#   We truncate oldest observations first to stay within budget.
#
# NOTE: No internet calls. All inference is local. API calls are commented out.
# =============================================================================

import configparser
import json
import logging
import re
import time
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# Optional LLM import — gracefully degrade if library not installed
try:
    from llama_cpp import Llama  # type: ignore[import]
    _LLAMA_AVAILABLE = True
except ImportError:
    log.warning("llama-cpp-python not installed — AI core running in stub mode.")
    _LLAMA_AVAILABLE = False


# =============================================================================
# Prompt templates
# =============================================================================

# System prompt: shapes the model into a cautious red-team assistant
SYSTEM_PROMPT = (
    "You are PentestGPT-lite, an offline AI pentesting assistant running on "
    "a Raspberry Pi. You help authorised security professionals test their own "
    "networks. You are cautious, methodical, and always explain your reasoning.\n"
    "Available tools: nmap_scan, wifi_crack, web_pentest, arp_spoof, sqlmap, "
    "hydra_brute, report_done.\n"
    "Respond ONLY in this format:\n"
    "Thought: <your reasoning>\n"
    "Action: <tool_name>(<args_as_json>)\n"
    "If the task is complete, output:\n"
    "Action: report_done({})\n"
)

# Risk scoring prompt: returns a single integer 1-10
RISK_PROMPT_TEMPLATE = (
    "Rate the security risk of this action on a scale of 1 (safe) to 10 "
    "(highly destructive/illegal). Respond with a single integer only.\n"
    "Action: {action}\nRisk score:"
)

# Maximum number of ReAct iterations (prevents infinite loops)
MAX_ITERATIONS = 10

# Token budget for conversation history before we start truncating
TOKEN_HISTORY_LIMIT = 400


# =============================================================================
# AICore class
# =============================================================================
class AICore:
    """
    Wraps llama-cpp-python with the ReAct prompt loop.
    Falls back to a rule-based stub if LLM is unavailable.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 512,
        n_threads: int = 3,
        cfg: Optional[configparser.ConfigParser] = None,
    ):
        self.cfg        = cfg or configparser.ConfigParser()
        self.max_risk   = int(self.cfg.get("security", "max_risk_score",  fallback="8"))
        self.confirm_th = int(self.cfg.get("security", "confirm_threshold", fallback="6"))
        self.max_tokens = int(self.cfg.get("llm", "max_tokens",   fallback="200"))
        self.temp       = float(self.cfg.get("llm", "temperature", fallback="0.3"))
        self.rep_pen    = float(self.cfg.get("llm", "repeat_penalty", fallback="1.1"))
        self._llm: Optional[Any] = None

        if _LLAMA_AVAILABLE:
            try:
                log.info("Loading LLM from %s (n_ctx=%d, threads=%d)",
                         model_path, n_ctx, n_threads)
                self._llm = Llama(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    verbose=False,   # Suppress llama.cpp debug spam
                )
                log.info("LLM loaded successfully.")
            except Exception as exc:
                log.error("LLM load error: %s", exc)
                self._llm = None
        else:
            log.warning("LLM unavailable — using rule-based stub.")

    # ── Internal LLM call ─────────────────────────────────────────────────────
    def _infer(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """
        Run LLM inference on `prompt`. Returns generated text.
        Falls back to stub response if LLM not loaded.

        IMPORTANT: No API calls. Fully local inference.
        """
        if self._llm is None:
            # Stub: return a simple scripted response for testing
            return self._stub_response(prompt)

        try:
            result = self._llm(
                prompt,
                max_tokens=max_tokens or self.max_tokens,
                temperature=self.temp,
                repeat_penalty=self.rep_pen,
                stop=["Observation:", "\nUser:", "\nHuman:"],
                echo=False,
            )
            text = result["choices"][0]["text"].strip()
            log.debug("LLM output: %s", text[:120])
            return text
        except Exception as exc:
            log.error("LLM inference error: %s", exc)
            return "Action: report_done({})"

    @staticmethod
    def _stub_response(prompt: str) -> str:
        """
        Rule-based stub response used when LLM is not available.
        Returns a scripted ReAct step for basic testing.
        """
        if "wifi" in prompt.lower():
            return ('Thought: I should scan for nearby access points.\n'
                    'Action: nmap_scan({"target": "192.168.1.0/24"})')
        if "web" in prompt.lower():
            return ('Thought: I should test the web application for SQL injection.\n'
                    'Action: sqlmap({"target": "http://127.0.0.1", "level": 1})')
        return ('Thought: I will perform a network reconnaissance sweep.\n'
                'Action: nmap_scan({"target": "192.168.1.0/24"})')

    # ── Risk scoring ──────────────────────────────────────────────────────────
    def score_risk(self, action_str: str) -> int:
        """
        Ask the LLM to rate the risk of a proposed action (1–10).
        Falls back to a heuristic if LLM unavailable.

        Risk scale:
          1-3  : Passive/read-only (nmap SYN scan, ARP ping)
          4-6  : Active but non-destructive (hydra, sqlmap read-only)
          7-9  : Potentially disruptive (DoS, deauth, exploit)
          10   : Destructive / illegal (system wipe, data deletion)
        """
        prompt = RISK_PROMPT_TEMPLATE.format(action=action_str)
        raw    = self._infer(prompt, max_tokens=4)
        # Extract first integer from response
        match  = re.search(r"\d+", raw)
        if match:
            score = int(match.group())
            return max(1, min(10, score))

        # Heuristic fallback
        return self._heuristic_risk(action_str)

    @staticmethod
    def _heuristic_risk(action_str: str) -> int:
        """
        Simple keyword-based risk heuristic.
        Used when LLM cannot parse the risk prompt.
        """
        action_lower = action_str.lower()
        if any(k in action_lower for k in ("deauth", "flood", "dos", "rm -rf",
                                            "exploit", "payload")):
            return 9
        if any(k in action_lower for k in ("hydra", "brute", "crack", "arp_spoof")):
            return 6
        if any(k in action_lower for k in ("sqlmap", "web_pentest")):
            return 5
        if any(k in action_lower for k in ("nmap", "scan", "recon")):
            return 3
        return 4

    # ── Response parser ───────────────────────────────────────────────────────
    @staticmethod
    def _parse_react_response(text: str) -> tuple[str, str, dict]:
        """
        Parse LLM output into (thought, action_name, action_args).
        Expected format:
            Thought: <text>
            Action: tool_name({"key": "value"})
        Returns ("", "", {}) on parse failure.
        """
        thought = ""
        action  = ""
        args: dict = {}

        # Extract Thought
        thought_match = re.search(r"Thought:\s*(.+?)(?=\nAction:|$)",
                                   text, re.DOTALL | re.IGNORECASE)
        if thought_match:
            thought = thought_match.group(1).strip()

        # Extract Action: tool_name({...})
        action_match = re.search(
            r"Action:\s*(\w+)\((\{.*?\})\)",
            text, re.DOTALL | re.IGNORECASE
        )
        if action_match:
            action    = action_match.group(1).strip()
            args_str  = action_match.group(2).strip()
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                log.warning("Could not parse action args: %s", args_str)
                args = {}
        else:
            # Fallback: action without args
            simple_match = re.search(r"Action:\s*(\w+)\(\)", text, re.IGNORECASE)
            if simple_match:
                action = simple_match.group(1).strip()

        return thought, action, args

    # ── Main ReAct loop ───────────────────────────────────────────────────────
    def react_loop(
        self,
        task: str,
        tools: Any,  # ToolRunner instance
        on_step: Optional[Callable[[dict], None]] = None,
    ) -> list[dict]:
        """
        Execute the Thought → Action → Observation → Next loop.

        Args:
            task     : Natural-language task description.
            tools    : ToolRunner instance with callable tool methods.
            on_step  : Optional callback invoked after each step (for OLED updates).

        Returns:
            List of result dicts from each tool execution.
        """
        log.info("ReAct loop starting. Task: %s", task)

        # Build initial prompt
        conversation = f"{SYSTEM_PROMPT}\nUser task: {task}\n"
        results: list[dict] = []

        for iteration in range(MAX_ITERATIONS):
            log.info("ReAct iteration %d/%d", iteration + 1, MAX_ITERATIONS)

            # Truncate conversation if too long (keep last TOKEN_HISTORY_LIMIT chars)
            if len(conversation) > TOKEN_HISTORY_LIMIT * 4:  # ~4 chars per token
                cutoff = len(conversation) - TOKEN_HISTORY_LIMIT * 4
                conversation = SYSTEM_PROMPT + "\n...[truncated]...\n" + \
                               conversation[cutoff:]

            # Generate next thought + action
            raw = self._infer(conversation)
            thought, action_name, action_args = self._parse_react_response(raw)

            log.info("Thought: %s | Action: %s | Args: %s",
                     thought[:60], action_name, action_args)

            # ── Termination check ─────────────────────────────────────────────
            if action_name == "report_done" or not action_name:
                log.info("ReAct loop complete (action: %s).", action_name)
                break

            # ── Risk assessment ───────────────────────────────────────────────
            action_str  = f"{action_name}({json.dumps(action_args)})"
            risk_score  = self.score_risk(action_str)
            log.info("Risk score for '%s': %d", action_name, risk_score)

            step_info = {
                "iteration": iteration,
                "thought":   thought,
                "action":    action_name,
                "args":      action_args,
                "risk":      risk_score,
            }

            # Notify OLED (non-blocking callback)
            if on_step:
                try:
                    on_step(step_info)
                except Exception as exc:
                    log.debug("on_step callback error: %s", exc)

            # ── Risk gate ─────────────────────────────────────────────────────
            if risk_score > self.max_risk:
                log.warning(
                    "Action '%s' skipped — risk %d > max_risk %d.",
                    action_name, risk_score, self.max_risk,
                )
                observation = (
                    f"Action '{action_name}' skipped (risk {risk_score} "
                    f"exceeds threshold {self.max_risk})."
                )
                results.append({**step_info, "skipped": True,
                                 "observation": observation})
                conversation += f"\nObservation: {observation}\n"
                continue

            # ── Execute tool ──────────────────────────────────────────────────
            observation, tool_results = self._execute_tool(
                action_name, action_args, tools
            )

            # Record result
            result_entry = {
                **step_info,
                "tool":        action_name,
                "command":     action_str,
                "output":      observation,
                "result_data": tool_results,
            }
            results.append(result_entry)

            # Append observation to conversation context
            conversation += (
                f"\nThought: {thought}\nAction: {action_str}\n"
                f"Observation: {observation[:300]}\n"
            )

            # Small delay to avoid hammering the CPU
            time.sleep(0.1)

        log.info("ReAct loop finished. %d results.", len(results))
        return results

    # ── Tool dispatcher ───────────────────────────────────────────────────────
    def _execute_tool(
        self, action: str, args: dict, tools: Any
    ) -> tuple[str, list]:
        """
        Dispatch action name to the appropriate ToolRunner method.
        Returns (observation_string, raw_result_list).
        """
        tool_map = {
            "nmap_scan":    tools.network_recon,
            "wifi_crack":   tools.wifi_crack,
            "web_pentest":  tools.web_pentest,
            "arp_spoof":    tools.arp_spoof,
            "sqlmap":       tools.sqlmap_scan,
            "hydra_brute":  tools.hydra_brute,
        }

        fn = tool_map.get(action)
        if fn is None:
            obs = f"Unknown action: {action}"
            log.warning(obs)
            return obs, []

        try:
            log.info("Executing tool: %s(%s)", action, args)
            raw = fn(**args) if args else fn()
            # Flatten list of dicts to a summary string for LLM context
            obs = self._summarise_results(raw)
            return obs, raw
        except TypeError as exc:
            # Argument mismatch — tool signature differs from args dict
            log.warning("Tool %s argument error: %s", action, exc)
            return f"Tool {action} argument error: {exc}", []
        except Exception as exc:
            log.error("Tool %s execution error: %s", action, exc)
            return f"Tool error: {exc}", []

    @staticmethod
    def _summarise_results(results: Any) -> str:
        """
        Convert raw tool output (list of dicts or string) to a
        concise observation string for the LLM context window.
        """
        if isinstance(results, str):
            return results[:300]

        if isinstance(results, list):
            parts = []
            for item in results[:5]:  # Max 5 items in context
                if isinstance(item, dict):
                    tool   = item.get("tool", "tool")
                    output = str(item.get("output", ""))[:100]
                    parts.append(f"[{tool}] {output}")
                else:
                    parts.append(str(item)[:100])
            return " | ".join(parts) or "No output."

        return str(results)[:300]
