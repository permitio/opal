package access.authentication.policy.deny.policy_0824

# Auto-generated policy 824
# Package: access.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0824",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0824 {
    input.user.role == "admin"
}
approved_0824 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0824 {
    input.user.active
    input.resource.public
}
denied_0824 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
