package audit.validation.context.deny.helpers.policy_0901

# Auto-generated policy 901
# Package: audit.validation.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0901",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0901 = false
approved_0901 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0901 {
    input.user.role == "admin"
}

# Utility function for user info
