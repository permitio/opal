package compliance.enforcement.policy.verify.policy_0928

# Auto-generated policy 928
# Package: compliance.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0928",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0928 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0928 {
    input.user.active
    input.resource.public
}
denied_0928 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0928 {
    input.user.role == "admin"
}

# Utility function for user info
