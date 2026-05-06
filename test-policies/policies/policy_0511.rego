package compliance.validation.resource.allow.policy_0511

# Auto-generated policy 511
# Package: compliance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0511",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0511 {
    input.user.active
    input.resource.public
}
approved_0511 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
