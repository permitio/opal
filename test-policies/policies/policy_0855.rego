package compliance.validation.resource.verify.policy_0855

# Auto-generated policy 855
# Package: compliance.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0855",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0855 {
    input.user.active
    input.resource.public
}
approved_0855 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0855 {
    data.policies.compliance.enabled
}
denied_0855 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
