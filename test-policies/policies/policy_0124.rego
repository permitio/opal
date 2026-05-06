package audit.authentication.policy.validate.data.policy_0124

# Auto-generated policy 124
# Package: audit.authentication.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0124",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0124 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0124 {
    input.user.active
    input.resource.public
}
denied_0124 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
