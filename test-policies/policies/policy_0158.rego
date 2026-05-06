package governance.enforcement.context.deny.policy_0158

# Auto-generated policy 158
# Package: governance.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0158",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0158 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0158 {
    data.policies.governance.enabled
}

# Utility function for user info
