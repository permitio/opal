package audit.monitoring.context.allow.helpers.policy_0410

# Auto-generated policy 410
# Package: audit.monitoring.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0410",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0410 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0410 {
    input.user.role == "admin"
}
approved_0410 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0410 {
    input.user.active
    input.resource.public
}

# Utility function for user info
