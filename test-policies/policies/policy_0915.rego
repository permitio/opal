package audit.monitoring.resource.deny.data.policy_0915

# Auto-generated policy 915
# Package: audit.monitoring.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0915",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0915 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0915 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0915 = false
allowed_0915 {
    input.user.role == "admin"
}

# Utility function for user info
