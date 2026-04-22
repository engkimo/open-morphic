"""CognitiveMemoryType — classification for Unified Cognitive Layer memory."""

from enum import Enum


class CognitiveMemoryType(str, Enum):
    EPISODIC = "episodic"  # What happened (events, actions, outcomes)
    SEMANTIC = "semantic"  # What is known (facts, entities, relationships)
    PROCEDURAL = "procedural"  # How to do things (strategies, patterns)
    WORKING = "working"  # Active context (current task state, decisions)
