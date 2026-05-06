package compliance.enforcement.user.deny.utils.policy_0622

# Auto-generated policy 622
# Package: compliance.enforcement.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0622",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0622 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0622 {
    input.user.active
    input.resource.public
}

# Utility function for user info
