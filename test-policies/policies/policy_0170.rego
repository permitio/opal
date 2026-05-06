package risk.authorization.user.verify.policy_0170

# Auto-generated policy 170
# Package: risk.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0170",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0170 {
    data.policies.risk.enabled
}
approved_0170 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0170 {
    input.user.role == "admin"
}
denied_0170 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
