package risk.validation.user.check.policy_0428

# Auto-generated policy 428
# Package: risk.validation.user.check

# Metadata
metadata := {
    "policy_id": "0428",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0428 {
    input.user.role == "admin"
}
approved_0428 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0428 {
    data.policies.risk.enabled
}
denied_0428 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
