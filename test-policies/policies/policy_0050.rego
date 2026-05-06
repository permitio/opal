package governance.validation.context.allow.utils.policy_0050

# Auto-generated policy 50
# Package: governance.validation.context.allow.utils

# Metadata
metadata := {
    "policy_id": "0050",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0050 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0050 {
    input.user.role == "admin"
}
default allowed_0050 = false
allowed_0050 {
    input.user.active
    input.resource.public
}

# Utility function for user info
