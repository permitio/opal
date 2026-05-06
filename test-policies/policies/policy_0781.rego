package access.validation.context.verify.data.policy_0781

# Auto-generated policy 781
# Package: access.validation.context.verify.data

# Metadata
metadata := {
    "policy_id": "0781",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0781 {
    input.user.role == "admin"
}
allowed_0781 {
    data.policies.access.enabled
}
approved_0781 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0781 {
    input.user.active
    input.resource.public
}

# Utility function for user info
