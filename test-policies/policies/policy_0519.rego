package governance.enforcement.context.allow.policy_0519

# Auto-generated policy 519
# Package: governance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0519",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0519 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0519 {
    data.policies.governance.enabled
}

# Utility function for user info
