package audit.authentication.context.check.data.policy_0927

# Auto-generated policy 927
# Package: audit.authentication.context.check.data

# Metadata
metadata := {
    "policy_id": "0927",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0927 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0927 {
    input.user.role == "admin"
}
approved_0927 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
