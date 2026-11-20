# Single source for the current_state bound (request validation + column width).
CURRENT_STATE_MAX_LENGTH = 255

# States the agent SDK's StateMachine emits today. The column stays opaque so
# agent-specific states need no platform change; this is the vocabulary a
# consumer can rely on being present.
KNOWN_CURRENT_STATES = ("IDLE", "WORKING", "AWAITING_INPUT")

CURRENT_STATE_DESCRIPTION = (
    "Opaque label mirroring the agent's StateMachine current state; null when the "
    "agent does not emit one. Orthogonal to 'status'. States the SDK emits today: "
    + ", ".join(KNOWN_CURRENT_STATES)
    + ". Treat any other value as unknown rather than assuming this set is closed."
)
