package security.authentication.context.verify.helpers.policy_0159

# Auto-generated policy 159
# Package: security.authentication.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0159",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0159 {
    data.policies.security.enabled
}
allowed_0159 {
    input.user.active
    input.resource.public
}
approved_0159 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0159 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
