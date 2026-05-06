package governance.validation.resource.allow.policy_0754

# Auto-generated policy 754
# Package: governance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0754",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0754 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0754 = false

# Utility function for user info
