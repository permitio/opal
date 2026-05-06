package security.enforcement.resource.verify.helpers.policy_0168

# Auto-generated policy 168
# Package: security.enforcement.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0168",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0168 {
    data.policies.security.enabled
}
allowed_0168 {
    input.user.role == "admin"
}
approved_0168 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0168 {
    input.user.active
    input.resource.public
}

# Utility function for user info
