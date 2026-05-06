package access.authentication.policy.check.policy_0547

# Auto-generated policy 547
# Package: access.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0547",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0547 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0547 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0547 {
    data.policies.access.enabled
}
allowed_0547 {
    input.user.active
    input.resource.public
}

# Utility function for user info
