package access.validation.action.verify.data.policy_0015

# Auto-generated policy 15
# Package: access.validation.action.verify.data

# Metadata
metadata := {
    "policy_id": "0015",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0015 {
    input.user.active
    input.resource.public
}
approved_0015 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0015 {
    input.user.role == "admin"
}
default allowed_0015 = false

# Utility function for user info
