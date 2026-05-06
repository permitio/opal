package governance.enforcement.resource.verify.policy_0708

# Auto-generated policy 708
# Package: governance.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0708",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0708 {
    input.user.role == "admin"
}
allowed_0708 {
    input.user.active
    input.resource.public
}
approved_0708 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
