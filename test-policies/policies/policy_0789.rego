package risk.authentication.policy.check.core.policy_0789

# Auto-generated policy 789
# Package: risk.authentication.policy.check.core

# Metadata
metadata := {
    "policy_id": "0789",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0789 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0789 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
