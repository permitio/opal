package governance.validation.context.deny.policy_0454

# Auto-generated policy 454
# Package: governance.validation.context.deny

# Metadata
metadata := {
    "policy_id": "0454",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0454 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0454 {
    input.user.active
    input.resource.public
}

# Utility function for user info
