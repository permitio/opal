package governance.validation.policy.deny.policy_0389

# Auto-generated policy 389
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0389",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0389 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0389 {
    input.user.active
    input.resource.public
}
default allowed_0389 = false
allowed_0389 {
    input.user.role == "admin"
}

# Utility function for user info
