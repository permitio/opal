package risk.validation.resource.check.data.policy_0363

# Auto-generated policy 363
# Package: risk.validation.resource.check.data

# Metadata
metadata := {
    "policy_id": "0363",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0363 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0363 {
    input.user.role == "admin"
}
approved_0363 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
