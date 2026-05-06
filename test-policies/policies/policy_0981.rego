package compliance.monitoring.user.deny.policy_0981

# Auto-generated policy 981
# Package: compliance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0981",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0981 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0981 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0981 {
    input.user.role == "admin"
}
allowed_0981 {
    input.user.active
    input.resource.public
}

# Utility function for user info
