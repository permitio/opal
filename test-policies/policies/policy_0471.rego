package governance.enforcement.policy.check.policy_0471

# Auto-generated policy 471
# Package: governance.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0471",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0471 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0471 {
    input.user.active
    input.resource.public
}
allowed_0471 {
    input.user.role == "admin"
}

# Utility function for user info
