package audit.authentication.action.allow.policy_0426

# Auto-generated policy 426
# Package: audit.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0426",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0426 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0426 {
    input.user.active
    input.resource.public
}

# Utility function for user info
