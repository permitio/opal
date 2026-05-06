package audit.authorization.resource.allow.policy_0748

# Auto-generated policy 748
# Package: audit.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0748",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0748 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0748 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0748 {
    data.policies.audit.enabled
}
allowed_0748 {
    input.user.role == "admin"
}

# Utility function for user info
