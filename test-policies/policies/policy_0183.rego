package access.validation.policy.verify.helpers.policy_0183

# Auto-generated policy 183
# Package: access.validation.policy.verify.helpers

# Metadata
metadata := {
    "policy_id": "0183",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0183 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0183 {
    input.user.active
    input.resource.public
}
allowed_0183 {
    data.policies.access.enabled
}
denied_0183 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
