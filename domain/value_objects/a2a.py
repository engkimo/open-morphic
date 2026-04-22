"""A2A (Agent-to-Agent) Protocol value objects.

Message types, actions, and conversation states for formal
inter-agent communication built on top of the UCL foundation.
"""

from enum import Enum


class A2AMessageType(str, Enum):
    """Type of A2A message in the protocol."""

    REQUEST = "request"  # Agent asks another to perform work
    RESPONSE = "response"  # Reply to a request
    BROADCAST = "broadcast"  # Inform all participants
    ACK = "ack"  # Acknowledge receipt
    ERROR = "error"  # Report a failure


class A2AAction(str, Enum):
    """What the sender is asking the receiver to do."""

    SOLVE = "solve"  # Perform the task
    REVIEW = "review"  # Review / QA an output
    SYNTHESIZE = "synthesize"  # Merge multiple outputs
    DELEGATE = "delegate"  # Pass to a more suitable agent
    CRITIQUE = "critique"  # Challenge / improve an answer
    INFORM = "inform"  # Share information (no action expected)


class A2AConversationStatus(str, Enum):
    """Lifecycle state of a multi-turn A2A conversation."""

    OPEN = "open"
    RESOLVED = "resolved"
    TIMEOUT = "timeout"
    ERROR = "error"
