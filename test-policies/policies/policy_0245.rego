package risk.authentication.context.check.core.policy_0245

# Auto-generated policy 245
# Package: risk.authentication.context.check.core

# Metadata
metadata := {
    "policy_id": "0245",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0245 {
    input.user.active
    input.resource.public
}
allowed_0245 {
    input.user.role == "admin"
}
denied_0245 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0245 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
