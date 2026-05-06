package access.validation.resource.deny.policy_0265

# Auto-generated policy 265
# Package: access.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0265",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0265 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0265 = false
denied_0265 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
