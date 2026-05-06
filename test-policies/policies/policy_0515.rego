package access.authentication.resource.validate.policy_0515

# Auto-generated policy 515
# Package: access.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0515",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0515 = false
approved_0515 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0515 {
    input.user.role == "admin"
}

# Utility function for user info
