package access.authorization.resource.deny.utils.policy_0105

# Auto-generated policy 105
# Package: access.authorization.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0105",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0105 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0105 {
    input.user.role == "admin"
}
allowed_0105 {
    data.policies.access.enabled
}

# Utility function for user info
