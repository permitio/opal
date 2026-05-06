package compliance.monitoring.context.deny.policy_0887

# Auto-generated policy 887
# Package: compliance.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0887",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0887 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0887 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0887 {
    data.policies.compliance.enabled
}
allowed_0887 {
    input.user.role == "admin"
}

# Utility function for user info
