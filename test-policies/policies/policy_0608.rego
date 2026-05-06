package governance.enforcement.context.allow.policy_0608

# Auto-generated policy 608
# Package: governance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0608",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0608 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0608 = false
allowed_0608 {
    input.user.active
    input.resource.public
}

# Utility function for user info
