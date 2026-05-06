package access.authentication.resource.validate.utils.policy_0550

# Auto-generated policy 550
# Package: access.authentication.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0550",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0550 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0550 {
    input.user.active
    input.resource.public
}
allowed_0550 {
    data.policies.access.enabled
}

# Utility function for user info
