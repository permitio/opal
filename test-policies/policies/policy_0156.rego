package access.monitoring.resource.deny.policy_0156

# Auto-generated policy 156
# Package: access.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0156",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0156 {
    input.user.active
    input.resource.public
}
approved_0156 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0156 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
