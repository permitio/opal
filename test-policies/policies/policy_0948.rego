package audit.authorization.user.deny.policy_0948

# Auto-generated policy 948
# Package: audit.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0948",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0948 {
    input.user.role == "admin"
}
denied_0948 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0948 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0948 {
    data.policies.audit.enabled
}

# Utility function for user info
