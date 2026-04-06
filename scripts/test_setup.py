#!/usr/bin/env python3
"""Test script to verify project setup."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        from core.config import settings
        print(f"  [OK] core.config (env: {settings.app_env})")
    except Exception as e:
        print(f"  [FAIL] core.config: {e}")

    try:
        from core.state import GraphState, AgentState
        print("  [OK] core.state")
    except Exception as e:
        print(f"  [FAIL] core.state: {e}")

    try:
        from core.orchestrator import Orchestrator
        print("  [OK] core.orchestrator")
    except Exception as e:
        print(f"  [FAIL] core.orchestrator: {e}")

    try:
        from agents.base_agent import BaseAgent, AgentState
        print("  [OK] agents.base_agent")
    except Exception as e:
        print(f"  [FAIL] agents.base_agent: {e}")

    try:
        from agents.intent_router import IntentRouter
        print("  [OK] agents.intent_router")
    except Exception as e:
        print(f"  [FAIL] agents.intent_router: {e}")

    try:
        from agents.language_agent import LanguageAgent
        print("  [OK] agents.language_agent")
    except Exception as e:
        print(f"  [FAIL] agents.language_agent: {e}")

    try:
        from llm.multi_llm_client import MultiLLMClient, LLMProvider
        print("  [OK] llm.multi_llm_client")
    except Exception as e:
        print(f"  [FAIL] llm.multi_llm_client: {e}")

    try:
        from rag.embeddings import EmbeddingClient
        print("  [OK] rag.embeddings")
    except Exception as e:
        print(f"  [FAIL] rag.embeddings: {e}")

    try:
        from rag.vector_store import VectorStore
        print("  [OK] rag.vector_store")
    except Exception as e:
        print(f"  [FAIL] rag.vector_store: {e}")

    try:
        from memory.memory_manager import MemoryManager
        print("  [OK] memory.memory_manager")
    except Exception as e:
        print(f"  [FAIL] memory.memory_manager: {e}")


def test_orchestrator():
    """Test orchestrator with a simple query."""
    print("\nTesting orchestrator...")

    try:
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        result = orch.process_query("Hola, ¿cómo estás?")

        print(f"  Input: 'Hola, ¿cómo estás?'")
        print(f"  Response: {result['response']}")
        print(f"  Agent: {result['agent_used']}")
        print(f"  Intent: {result['intent']}")
        print(f"  Language: {result['language']}")
        print(f"  Time: {result['processing_time_ms']}ms")
        print("  [OK] Orchestrator working")

    except Exception as e:
        print(f"  [FAIL] Orchestrator: {e}")


def test_intent_router():
    """Test intent classification."""
    print("\nTesting intent router...")

    try:
        from agents.intent_router import IntentRouter

        router = IntentRouter()

        test_cases = [
            ("Hola!", "GREETING"),
            ("What is Program H?", "FACTUAL"),
            ("How can I implement this activity?", "PLAN"),
            ("Give me creative ideas", "IDEATE"),
        ]

        for text, expected in test_cases:
            result = router.classify(text)
            status = "[OK]" if result["intent"] == expected else "[?]"
            print(f"  {status} '{text[:30]}...' -> {result['intent']} (expected: {expected})")

    except Exception as e:
        print(f"  [FAIL] Intent router: {e}")


def test_language_detection():
    """Test language detection."""
    print("\nTesting language detection...")

    try:
        from agents.language_agent import LanguageAgent

        agent = LanguageAgent()

        test_cases = [
            ("Hola, ¿cómo estás?", "es"),
            ("Hello, how are you?", "en"),
            ("Olá, como você está?", "pt"),
        ]

        for text, expected in test_cases:
            result = agent.detect(text)
            status = "[OK]" if result["language"] == expected else "[?]"
            print(f"  {status} '{text}' -> {result['language']} (expected: {expected})")

    except Exception as e:
        print(f"  [FAIL] Language detection: {e}")


def main():
    """Run all tests."""
    print("=" * 50)
    print("Agent Chat Builder - Setup Test")
    print("=" * 50)

    test_imports()
    test_orchestrator()
    test_intent_router()
    test_language_detection()

    print("\n" + "=" * 50)
    print("Setup test complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
