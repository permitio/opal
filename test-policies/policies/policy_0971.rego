package security.authentication.resource.deny.data.policy_0971

# Auto-generated policy 971
# Package: security.authentication.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0971",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0971 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0971 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0971 {
    input.user.active
    input.resource.public
}
allowed_0971 {
    data.policies.security.enabled
}

# Utility function for user info
