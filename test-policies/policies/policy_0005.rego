package risk.validation.context.check.helpers.policy_0005

# Auto-generated policy 5
# Package: risk.validation.context.check.helpers

# Metadata
metadata := {
    "policy_id": "0005",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0005 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0005 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0005 {
    input.user.role == "admin"
}

# Utility function for user info
