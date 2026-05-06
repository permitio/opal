package access.authorization.user.check.policy_0617

# Auto-generated policy 617
# Package: access.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0617",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0617 {
    input.user.active
    input.resource.public
}
allowed_0617 {
    input.user.role == "admin"
}
approved_0617 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0617 {
    data.policies.access.enabled
}

# Utility function for user info
