# Operating Modes Guide

## Overview

The Personal AI Assistant supports multiple operating modes that can be selected automatically or manually based on the query type.

## Conversation Mode

### When to Use

- Questions requiring simple information retrieval
- Casual conversation
- Quick advice or clarification
- Commands to execute actions
- Explanations of concepts

### Characteristics

- **Speed**: 100-500ms response time
- **Reasoning**: Minimal; direct LLM call
- **Deliberation**: None
- **Confidence**: Single point prediction
- **Best for**: Time-sensitive interactions

### Example

```
User: "What's the capital of France?"
→ Conversation Mode
→ Direct LLM call
→ Response: "Paris is the capital of France..."
→ Time: 250ms
```

### Implementation Details

Located in `backend/modes/conversation/`:

- `engine.py`: Main conversation logic
- `schemas.py`: Request/response models
- `router.py`: API endpoints

## Decision Mode (MAGI)

### When to Use

- Complex decisions with multiple factors
- Choices involving trade-offs
- Situations requiring reasoning justification
- Preference between alternatives
- High-stakes decisions (career, finance, etc.)

### Characteristics

- **Speed**: 5-30s per decision
- **Reasoning**: 5-stage multi-agent pipeline
- **Deliberation**: Structured debate
- **Confidence**: Voting-based consensus
- **Best for**: Well-reasoned, justified answers

### The MAGI Pipeline

1. **World Model Stage**
   - Raw user input → Structured situation understanding
   - Creates normalized representation of problem

2. **Action Generation**
   - Situation → Candidate actions (3-5 options)
   - Options normalized and stable

3. **Brain Evaluation (Round 1)**
   - Each of three brains evaluates actions
   - Brains: SARASWATI, LAKSHMI, DURGA
   - Each returns: selected action, confidence, reason, risk

4. **Debate Round**
   - Brains see each other's positions
   - Can change minds
   - Provides new reasoning

5. **Voting**
   - Final votes from each brain
   - Python determines majority
   - Tie-breaking logic

6. **Chair Summary**
   - VIVEKA agent synthesizes everything
   - Creates final summary and recommendation
   - Provides dominant reasoning

### Example

```
User: "Should I accept this job offer?"
Goal: "Find fulfilling work"
Constraints: ["Need flexible hours", "Interested in AI"]

→ Decision Mode (MAGI)
→ World Model: Creates structured understanding
→ Actions Generated: 
    - ACTION_1: Accept and relocate
    - ACTION_2: Negotiate flexible terms
    - ACTION_3: Decline and keep searching
    - ACTION_4: Ask for trial period
→ Brain Round 1: Each agent evaluates
→ Debate: Agents react to each other
→ Voting: Final decisions
→ Chair Summary: Final recommendation
→ Time: 12-15 seconds
```

### Brain Personalities

- **SARASWATI** (Logic) - Analytical, fact-based reasoning
- **LAKSHMI** (Emotion) - Values-based, intuition-driven
- **DURGA** (Determination) - Action-oriented, risk-taking
- **VIVEKA** (Wisdom) - Synthesizes and provides final summary

## Auto-Mode Selection

The router automatically selects mode based on keywords:

### Decision Keywords

```
decide, should, which, best, recommend,
pros and cons, compare, evaluate, debate,
consider, analyze, choice, opinion, advice
```

If query contains any of these → Decision Mode

Otherwise → Conversation Mode

### Manual Override

```json
{
  "query": "Capital of France?",
  "mode": "conversation"  // Force conversation
}
```

or

```json
{
  "query": "Should I move to Paris?",
  "mode": "decision"  // Force decision
}
```

## Mode Switching

The router can switch modes mid-session:

```
Session starts → Conversation mode active

User: "Should I relocate?"
→ Auto-detects decision keywords
→ Switches to decision mode
→ Runs MAGI pipeline
→ Switches back to conversation mode

User: "Tell me more about that"
→ Conversation mode handles follow-up
```

## Expected Response Structure

### Conversation Response

```json
{
  "mode": "conversation",
  "answer": "Paris is the capital and most populous...",
  "confidence": 0.95,
  "follow_up_suggestions": [
    "Tell me about French culture",
    "What are popular attractions?",
    "When's the best time to visit?"
  ],
  "processing_time_ms": 245
}
```

### Decision Response

```json
{
  "mode": "decision",
  "answer": "Based on the council's deliberation...",
  "reasoning": "The agents agreed that option 2 best balances...",
  "decision_data": {
    "final_decision": "ACTION_2",
    "recommended_action": "Negotiate flexible terms",
    "full_result": {
      "situation_model": {...},
      "action_set": {...},
      "first_round": {...},
      "debate_round": {...},
      "votes": {...},
      "chair_summary": {...}
    }
  },
  "processing_time_ms": 14200
}
```

## Performance Tuning

### Conversation Mode

- Adjust temperature (lower = more focused, higher = more creative)
- Set personality parameter
- Control context window size
- Implement caching for common questions

### Decision Mode

- Adjust individual brain temperatures
- Tune debate round iterations
- Modify action generation limits (3-5 actions)
- Implement early stopping if consensus reached

## Future Modes (Planned)

- **Research Mode**: Deep web research with external sources
- **Creation Mode**: Brainstorming and ideation with multiple perspectives
- **Tutorial Mode**: Step-by-step guided assistance
- **Expert Mode**: Specialized reasoning for domain knowledge
- **Adaptive Mode**: Mode selection based on user preferences over time

## Integration with Other Subsystems

### Voice Integration

Voice input → Text → Route through modes → Voice output of response

### Action Integration

Actions selected in modes can be executed afterward:

```
Decision Mode → Recommends action "Open project X in VS Code"
→ Can be passed to Action Executor
→ Executes system command
```

### Memory Integration

Conversation and decision histories stored for context:

```
Mode sees past decisions and conversations
→ Better context for new requests
→ Learns user preferences
→ Adapts responses over time
```

## Switching Between Modes Programmatically

```python
from backend.core.router import AssistantRouter

router = AssistantRouter()

# Switch to decision mode
await router.set_active_mode("decision")

# Make a request
response = await router.route(request)

# Switch back
await router.set_active_mode("conversation")
```

## Monitoring and Logging

All mode operations are logged:

```
[INFO] Routing to mode: conversation
[DEBUG] Query processed in conversation engine
[INFO] Active mode switched to: decision
[DEBUG] MAGI pipeline started...
[INFO] Decision completed in 12.5s
```

Check logs in `logs/app.log` and `logs/errors.log`
