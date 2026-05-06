package audit.authentication.resource.validate.policy_0522

# Auto-generated policy 522
# Package: audit.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0522",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0522 {
    input.user.active
    input.resource.public
}
allowed_0522 {
    data.policies.audit.enabled
}
approved_0522 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0522 = false

# Utility function for user info
