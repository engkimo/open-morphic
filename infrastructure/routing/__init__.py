"""Goal-classifier routing adapters.

Houses `LLMGoalClassifier` (remote) and `LocalGoalClassifier` (Ollama) plus
the shared stable prompt + parser used by both. Both impls satisfy
``domain.ports.goal_classifier.GoalClassifierPort``.
"""
