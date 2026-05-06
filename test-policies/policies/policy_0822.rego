package access.enforcement.context.deny.policy_0822

# Auto-generated policy 822
# Package: access.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0822",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0822 {
    input.user.active
    input.resource.public
}
approved_0822 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0822 {
    input.user.role == "admin"
}

# Utility function for user info
